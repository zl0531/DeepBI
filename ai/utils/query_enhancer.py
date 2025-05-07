#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Query Enhancer for DeepBI

This module provides functions to enhance SQL queries by matching user query terms
to actual database values. It helps bridge the gap between how users refer to data
and how it's actually stored in the database.
"""

import re
import logging
import psycopg2
import pandas as pd
from difflib import SequenceMatcher
import traceback
from typing import Dict, List, Tuple, Optional, Set

# Import the entity mapper if available
try:
    from entity_mapper import SchemaEntityMapper, CommentParser, EntityMapper
    ENTITY_MAPPER_AVAILABLE = True
except ImportError:
    ENTITY_MAPPER_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QueryEnhancer:
    """
    A class to enhance SQL queries by matching user query terms to actual database values.
    """

    def __init__(self, connection_params, schema_info=None):
        """
        Initialize the QueryEnhancer with database connection parameters.

        Args:
            connection_params: Dictionary with database connection parameters
            schema_info: Optional dictionary with schema information
        """
        self.connection_params = connection_params
        self.schema_entity_mapper = None

        # Initialize entity mapper if schema info is provided and entity mapper is available
        if schema_info and ENTITY_MAPPER_AVAILABLE:
            try:
                self.schema_entity_mapper = SchemaEntityMapper(schema_info)
                logger.info("Initialized schema entity mapper")
            except Exception as e:
                logger.error(f"Error initializing schema entity mapper: {str(e)}")
                traceback.print_exc()

    def get_connection(self):
        """Get a database connection"""
        return psycopg2.connect(**self.connection_params)

    def get_table_columns(self, table_name):
        """
        Get all columns for a given table.

        Args:
            table_name: Name of the table

        Returns:
            List of column names
        """
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (table_name,))

            columns = [row[0] for row in cursor.fetchall()]
            cursor.close()
            connection.close()

            return columns
        except Exception as e:
            logger.error(f"Error getting table columns: {str(e)}")
            return []

    def get_distinct_values(self, table_name, column_name):
        """
        Get all distinct values for a column in a table.

        Args:
            table_name: Name of the table
            column_name: Name of the column

        Returns:
            List of distinct values
        """
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute(f"SELECT DISTINCT {column_name} FROM {table_name}")
            values = [row[0] for row in cursor.fetchall()]

            cursor.close()
            connection.close()

            return values
        except Exception as e:
            logger.error(f"Error getting distinct values: {str(e)}")
            return []

    def similarity_score(self, a, b):
        """Calculate string similarity score between 0 and 1"""
        return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

    def find_best_matches(self, search_terms, candidates, threshold=0.6):
        """
        Find the best matches for search terms among candidates.

        Args:
            search_terms: List of terms to search for
            candidates: List of candidate values to match against
            threshold: Minimum similarity score to consider a match

        Returns:
            Dictionary mapping search terms to best matching candidates
        """
        matches = {}

        for term in search_terms:
            term_str = str(term).lower()

            # Try exact match first
            exact_matches = [c for c in candidates if str(c).lower() == term_str]
            if exact_matches:
                matches[term] = exact_matches[0]
                continue

            # Try contains match
            contains_matches = [c for c in candidates if term_str in str(c).lower()]
            if contains_matches:
                # Sort by length to prefer shorter matches
                matches[term] = sorted(contains_matches, key=lambda x: len(str(x)))[0]
                continue

            # Try fuzzy matching
            scores = [(c, self.similarity_score(term, c)) for c in candidates]
            best_matches = sorted(scores, key=lambda x: x[1], reverse=True)

            if best_matches and best_matches[0][1] >= threshold:
                matches[term] = best_matches[0][0]
            else:
                matches[term] = None

        return matches

    def extract_comparison_terms(self, query_text, column_name=None):
        """
        Extract terms that the user wants to compare from the query text.
        If a schema entity mapper is available, it will be used to map terms to canonical forms.

        Args:
            query_text: The user's query text
            column_name: Optional column name to use for entity mapping

        Returns:
            List of terms to compare
        """
        # Look for terms in quotes
        quoted_terms = re.findall(r'"([^"]*)"', query_text)
        quoted_terms.extend(re.findall(r"'([^']*)'", query_text))

        # Look for terms after "compare" or "对比"
        compare_terms = []
        compare_patterns = [
            r'compare\s+([^,]+)\s+and\s+([^,\.]+)',
            r'对比\s+([^,]+)\s+和\s+([^,\.]+)',
            r'比较\s+([^,]+)\s+和\s+([^,\.]+)',
            r'between\s+([^,]+)\s+and\s+([^,\.]+)'
        ]

        for pattern in compare_patterns:
            matches = re.findall(pattern, query_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    compare_terms.extend(match)
                else:
                    compare_terms.append(match)

        # Combine and clean up terms
        all_terms = quoted_terms + compare_terms
        cleaned_terms = [term.strip() for term in all_terms if term.strip()]

        # If we couldn't extract terms, look for capitalized words or abbreviations
        if not cleaned_terms:
            # Look for abbreviations in parentheses
            abbrev_terms = re.findall(r'\(([A-Z]{2,})\)', query_text)
            cleaned_terms.extend(abbrev_terms)

            # Look for capitalized words that might be entity names
            cap_words = re.findall(r'\b([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)\b', query_text)
            cleaned_terms.extend(cap_words)

            # Look for Chinese characters that might be entity names
            chinese_terms = re.findall(r'([\u4e00-\u9fff]+)', query_text)
            cleaned_terms.extend(chinese_terms)

        # Remove duplicates
        cleaned_terms = list(set(cleaned_terms))

        # Map terms to canonical forms if entity mapper is available
        if self.schema_entity_mapper and column_name and self.schema_entity_mapper.has_mapper_for_column(column_name):
            mapped_terms = []

            for term in cleaned_terms:
                canonical_form = self.schema_entity_mapper.get_canonical_form(column_name, term)
                if canonical_form:
                    logger.info(f"Mapped term '{term}' to canonical form '{canonical_form}'")
                    mapped_terms.append(canonical_form)
                else:
                    mapped_terms.append(term)

            return mapped_terms

        return cleaned_terms

    def enhance_query(self, original_query, user_query_text, table_name, column_name):
        """
        Enhance a SQL query by replacing search terms with actual database values.

        Args:
            original_query: The original SQL query with placeholders
            user_query_text: The user's natural language query
            table_name: The database table to query
            column_name: The column containing values to match

        Returns:
            Enhanced SQL query with actual database values
        """
        try:
            # If we have a schema entity mapper, use it to get canonical forms
            if self.schema_entity_mapper and self.schema_entity_mapper.has_mapper_for_column(column_name):
                logger.info(f"Using schema entity mapper for column {column_name}")

                # Extract terms and map them to canonical forms
                search_terms = self.extract_comparison_terms(user_query_text, column_name)
                logger.info(f"Extracted and mapped search terms: {search_terms}")

                if not search_terms:
                    logger.warning("No search terms extracted from query")
                    return original_query, []

                # Get all canonical forms for this column
                all_canonical_forms = self.schema_entity_mapper.get_all_canonical_forms(column_name)
                logger.info(f"All canonical forms for column {column_name}: {all_canonical_forms}")

                # Filter search terms to only include canonical forms
                actual_values = [term for term in search_terms if term in all_canonical_forms]

                if not actual_values:
                    logger.warning("No valid canonical forms found in search terms")

                    # Fall back to using the database values
                    db_values = self.get_distinct_values(table_name, column_name)
                    matches = self.find_best_matches(search_terms, db_values)
                    valid_matches = {term: value for term, value in matches.items() if value is not None}

                    if not valid_matches:
                        logger.warning("No valid matches found for search terms")
                        return original_query, []

                    actual_values = list(valid_matches.values())
            else:
                # Use the original approach
                logger.info(f"Using database matching for column {column_name}")

                # Extract terms to compare from the user's query
                search_terms = self.extract_comparison_terms(user_query_text)
                logger.info(f"Extracted search terms: {search_terms}")

                if not search_terms:
                    logger.warning("No search terms extracted from query")
                    return original_query, []

                # Get actual values from the database
                db_values = self.get_distinct_values(table_name, column_name)
                logger.info(f"Found {len(db_values)} distinct values in {column_name}")

                # Find best matches for search terms
                matches = self.find_best_matches(search_terms, db_values)
                logger.info(f"Term matches: {matches}")

                # Filter out terms with no matches
                valid_matches = {term: value for term, value in matches.items() if value is not None}

                if not valid_matches:
                    logger.warning("No valid matches found for search terms")
                    return original_query, []

                # Get the actual values to use in the query
                actual_values = list(valid_matches.values())

            # Create a dynamic CASE statement based on the actual values
            case_clauses_select = []
            case_clauses_group = []

            for i, value in enumerate(actual_values):
                # Extract abbreviation from value if it contains parentheses
                abbrev_match = re.search(r'\(([A-Z]+)\)', value)
                display_name = abbrev_match.group(1) if abbrev_match else f"Value{i+1}"

                case_clauses_select.append(f"WHEN {column_name} = %s THEN '{display_name}'")
                case_clauses_group.append(f"WHEN {column_name} = %s THEN '{display_name}'")

            case_statement_select = f"CASE {' '.join(case_clauses_select)} ELSE {column_name} END as display_name"
            case_statement_group = f"CASE {' '.join(case_clauses_group)} ELSE {column_name} END"

            # Create a completely new query that uses exact matching and proper grouping
            new_query = f"""
            SELECT model_year,
                   {case_statement_select},
                   COUNT(*) as count
            FROM {table_name}
            WHERE {column_name} IN ({', '.join(['%s'] * len(actual_values))})
            GROUP BY model_year,
                     {case_statement_group}
            ORDER BY model_year
            """

            # Create the parameter list - we need to repeat the values for the CASE statements
            params = []
            params.extend(actual_values)  # For the CASE in SELECT
            params.extend(actual_values)  # For the IN clause
            params.extend(actual_values)  # For the CASE in GROUP BY

            logger.info(f"Created new query: {new_query}")
            logger.info(f"With parameters: {params}")

            return new_query, params
        except Exception as e:
            logger.error(f"Error enhancing query: {str(e)}")
            traceback.print_exc()
            return original_query, []

    def execute_enhanced_query(self, query, params, user_query_text, table_name, column_name, schema_info=None):
        """
        Execute an enhanced query with proper parameter substitution.

        Args:
            query: The SQL query with placeholders
            params: Parameters for the original query
            user_query_text: The user's natural language query
            table_name: The database table to query
            column_name: The column containing values to match
            schema_info: Optional dictionary with schema information

        Returns:
            Pandas DataFrame with query results
        """
        try:
            # If schema info is provided and we don't have a schema entity mapper yet, initialize it
            if schema_info and not self.schema_entity_mapper and ENTITY_MAPPER_AVAILABLE:
                try:
                    self.schema_entity_mapper = SchemaEntityMapper(schema_info)
                    logger.info("Initialized schema entity mapper")
                except Exception as e:
                    logger.error(f"Error initializing schema entity mapper: {str(e)}")
                    traceback.print_exc()

            # Enhance the query
            enhanced_query, actual_values = self.enhance_query(query, user_query_text, table_name, column_name)

            if not actual_values:
                logger.warning("No actual values found, using original query")
                connection = self.get_connection()
                df = pd.read_sql(query, con=connection, params=params)
                connection.close()
                return df

            # Execute the enhanced query
            connection = self.get_connection()
            df = pd.read_sql(enhanced_query, con=connection, params=actual_values)
            connection.close()

            return df
        except Exception as e:
            logger.error(f"Error executing enhanced query: {str(e)}")
            traceback.print_exc()

            # Fall back to original query
            try:
                connection = self.get_connection()
                df = pd.read_sql(query, con=connection, params=params)
                connection.close()
                return df
            except Exception as e2:
                logger.error(f"Error executing original query: {str(e2)}")
                return pd.DataFrame()

# Example usage
if __name__ == "__main__":
    # Example database connection parameters
    connection_params = {
        "dbname": "postgres",
        "user": "postgres",
        "password": "",
        "host": "postgres",
        "port": "5432"
    }

    enhancer = QueryEnhancer(connection_params)

    # Example query
    original_query = """
    SELECT model_year, electric_vehicle_type, COUNT(*) as count
    FROM electric_vehicles
    WHERE electric_vehicle_type IN ('BEV', 'PHEV')
    GROUP BY model_year, electric_vehicle_type
    ORDER BY model_year
    """

    # Example user query
    user_query = "用图表对比 Battery Electric Vehicle (BEV) 和 Plug-in Hybrid Electric Vehicle (PHEV)电动车的销量趋势"

    # Enhance and execute the query
    df = enhancer.execute_enhanced_query(
        original_query,
        [],
        user_query,
        "electric_vehicles",
        "electric_vehicle_type"
    )

    print(df.head())
