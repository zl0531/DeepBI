#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script to fix MySQL schema retrieval in DeepBI

This script creates a patched version of the MySQL query runner that uses
SHOW TABLES and SHOW COLUMNS instead of querying information_schema.
"""

import os
import shutil
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to the MySQL query runner
MYSQL_RUNNER_PATH = "bi/query_runner/mysql.py"

# Backup the original file
def backup_file(file_path):
    backup_path = file_path + ".bak"
    if not os.path.exists(backup_path):
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup at {backup_path}")
    else:
        logger.info(f"Backup already exists at {backup_path}")

# The new _get_tables implementation
NEW_GET_TABLES_CODE = """
    def _get_tables(self, schema):
        \"\"\"
        Retrieve schema information using SHOW TABLES and SHOW COLUMNS
        instead of querying information_schema.
        \"\"\"
        try:
            connection = self._connection()
            cursor = connection.cursor()

            # Get list of tables
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]

            # Get columns for each table
            for table_name in tables:
                if table_name not in schema:
                    schema[table_name] = {"name": table_name, "columns": [], 'comment': []}

                try:
                    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
                    columns = [row[0] for row in cursor.fetchall()]

                    for column in columns:
                        schema[table_name]["columns"].append(column)
                        # Since we can't easily get column comments with SHOW COLUMNS,
                        # we'll just use empty strings
                        schema[table_name]["comment"].append("")
                except Exception as e:
                    logger.error(f"Error getting columns for table {table_name}: {str(e)}")

            cursor.close()
            connection.close()

        except Exception as e:
            logger.error(f"Error in _get_tables: {str(e)}")

        return list(schema.values())
"""

def patch_mysql_runner():
    # Check if the file exists
    if not os.path.exists(MYSQL_RUNNER_PATH):
        logger.error(f"MySQL query runner not found at {MYSQL_RUNNER_PATH}")
        return False

    # Backup the file
    backup_file(MYSQL_RUNNER_PATH)

    # Read the file
    with open(MYSQL_RUNNER_PATH, 'r') as f:
        content = f.read()

    # Find the _get_tables method
    start_marker = "    def _get_tables(self, schema):"
    end_marker = "        return list(schema.values())"

    start_pos = content.find(start_marker)
    if start_pos == -1:
        logger.error("Could not find _get_tables method in the file")
        return False

    end_pos = content.find(end_marker, start_pos)
    if end_pos == -1:
        logger.error("Could not find the end of _get_tables method")
        return False

    # Include the end marker in the replacement
    end_pos += len(end_marker)

    # Replace the method
    new_content = content[:start_pos] + NEW_GET_TABLES_CODE + content[end_pos:]

    # Write the new content
    with open(MYSQL_RUNNER_PATH, 'w') as f:
        f.write(new_content)

    logger.info(f"Successfully patched {MYSQL_RUNNER_PATH}")
    return True

def main():
    logger.info("Starting MySQL schema fix")
    if patch_mysql_runner():
        logger.info("Patch applied successfully")
        logger.info("Please restart the DeepBI server for changes to take effect")
    else:
        logger.error("Failed to apply patch")

if __name__ == "__main__":
    main()
