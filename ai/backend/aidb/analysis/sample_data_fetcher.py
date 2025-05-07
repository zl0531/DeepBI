#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sample Data Fetcher for DeepBI

This module provides functions to fetch sample data from database tables
to include in the context provided to the LLM.
"""

import logging
import psycopg2
import pandas as pd
from typing import Dict, List, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SampleDataFetcher:
    """
    A class to fetch sample data from database tables.
    """
    
    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize the SampleDataFetcher with database connection parameters.
        
        Args:
            connection_params: Dictionary with database connection parameters
        """
        self.connection_params = connection_params
    
    def get_connection(self):
        """Get a database connection"""
        return psycopg2.connect(**self.connection_params)
    
    def fetch_sample_data(self, table_name: str, columns: Optional[List[str]] = None, 
                         limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch sample data from a table.
        
        Args:
            table_name: Name of the table
            columns: Optional list of column names to fetch (defaults to all columns)
            limit: Maximum number of rows to fetch
            
        Returns:
            List of dictionaries with sample data
        """
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Build the query
            columns_str = "*" if not columns else ", ".join(columns)
            query = f"SELECT {columns_str} FROM {table_name} LIMIT {limit}"
            
            # Execute the query
            cursor.execute(query)
            
            # Get column names
            column_names = [desc[0] for desc in cursor.description]
            
            # Fetch the data
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            result = []
            for row in rows:
                row_dict = {}
                for i, value in enumerate(row):
                    row_dict[column_names[i]] = value
                result.append(row_dict)
            
            cursor.close()
            connection.close()
            
            return result
        except Exception as e:
            logger.error(f"Error fetching sample data: {str(e)}")
            return []
    
    def format_sample_data_as_table(self, sample_data: List[Dict[str, Any]]) -> str:
        """
        Format sample data as a markdown table.
        
        Args:
            sample_data: List of dictionaries with sample data
            
        Returns:
            Markdown table string
        """
        if not sample_data:
            return "No sample data available."
        
        # Get column names
        columns = list(sample_data[0].keys())
        
        # Build the header
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"
        
        # Build the rows
        rows = []
        for row in sample_data:
            row_str = "| " + " | ".join([str(row.get(col, "")) for col in columns]) + " |"
            rows.append(row_str)
        
        # Combine everything
        table = "\n".join([header, separator] + rows)
        
        return table
    
    def get_sample_data_for_schema(self, schema_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Get sample data for all tables in a schema.
        
        Args:
            schema_info: Dictionary with schema information
            
        Returns:
            Dictionary mapping table names to sample data tables
        """
        result = {}
        
        if 'table_desc' not in schema_info:
            return result
        
        for table in schema_info['table_desc']:
            if 'table_name' not in table:
                continue
            
            table_name = table['table_name']
            
            # Get column names
            columns = None
            if 'field_desc' in table:
                columns = [field['name'] for field in table['field_desc'] if 'name' in field]
            
            # Fetch sample data
            sample_data = self.fetch_sample_data(table_name, columns)
            
            # Format as table
            sample_data_table = self.format_sample_data_as_table(sample_data)
            
            # Add to result
            result[table_name] = sample_data_table
        
        return result

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
    
    # Example schema info
    schema_info = {
        'table_desc': [
            {
                'table_name': 'electric_vehicles',
                'field_desc': [
                    {'name': 'electric_vehicle_type'},
                    {'name': 'model_year'}
                ]
            }
        ]
    }
    
    # Initialize sample data fetcher
    fetcher = SampleDataFetcher(connection_params)
    
    # Get sample data for schema
    sample_data = fetcher.get_sample_data_for_schema(schema_info)
    
    # Print the result
    for table_name, table_data in sample_data.items():
        print(f"Sample data for table {table_name}:")
        print(table_data)
        print()
