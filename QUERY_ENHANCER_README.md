# Query Enhancer for DeepBI

This document explains how to use the Query Enhancer to solve the issue with empty charts in DeepBI when user queries don't exactly match database values.

## Problem Description

In DeepBI, when users request charts comparing different entities (like "BEV" and "PHEV" electric vehicles), the system generates SQL queries that use these exact terms in the WHERE clause. However, if the database stores these entities with different names (like "Battery Electric Vehicle (BEV)" instead of just "BEV"), the query returns no results, leading to empty charts.

## Solution: Query Enhancer

The Query Enhancer is a general solution that:

1. Analyzes the user's query to identify what entities they want to compare
2. Searches the database to find the actual column values that best match these entities
3. Uses those actual values in the SQL query

This approach works for any type of data, not just electric vehicles.

## How It Works

1. When a chart is generated with empty data, the system automatically tries to enhance the query
2. It extracts the SQL query from the chart code
3. It identifies the table name and column name from the query
4. It extracts comparison terms from the user's original question
5. It searches the database for values that best match these terms
6. It replaces the original query with an enhanced version using the actual database values

## Implementation

The solution consists of two main components:

1. **query_enhancer.py**: A utility class that handles the query enhancement logic
2. **Patches to analysis_pg.py**: Code that integrates the query enhancer into the chart generation process

### Using the Query Enhancer in Custom Code

You can use the Query Enhancer in your own code like this:

```python
from query_enhancer import QueryEnhancer

# Database connection parameters
connection_params = {
    "dbname": "your_dbname",
    "user": "your_username",
    "password": "your_password",
    "host": "your_host",
    "port": "your_port"
}

# Initialize the query enhancer
enhancer = QueryEnhancer(connection_params)

# Original query with placeholders
original_query = """
SELECT model_year, column_name, COUNT(*) as count
FROM table_name
WHERE column_name IN (%s, %s)
GROUP BY model_year, column_name
ORDER BY model_year
"""

# User's natural language query
user_query = "Compare Entity1 and Entity2 over time"

# Execute the enhanced query
df = enhancer.execute_enhanced_query(
    original_query, 
    [], 
    user_query, 
    "table_name", 
    "column_name"
)
```

### Key Features

1. **Term Extraction**: Extracts comparison terms from natural language queries using various patterns
2. **Fuzzy Matching**: Uses string similarity to find the best matches for terms
3. **Fallback Mechanism**: Falls back to the original query if enhancement fails
4. **Logging**: Provides detailed logs for debugging

## Example

### User Query
```
用图表对比 Battery Electric Vehicle (BEV) 和 Plug-in Hybrid Electric Vehicle (PHEV)电动车的销量趋势
```

### Original SQL Query
```sql
SELECT model_year, electric_vehicle_type, COUNT(*) as sales_count
FROM electric_vehicles
WHERE electric_vehicle_type IN ('BEV', 'PHEV')
GROUP BY model_year, electric_vehicle_type
ORDER BY model_year
```

### Enhanced SQL Query
```sql
SELECT model_year, electric_vehicle_type, COUNT(*) as sales_count
FROM electric_vehicles
WHERE electric_vehicle_type IN ('Battery Electric Vehicle (BEV)', 'Plug-in Hybrid Electric Vehicle (PHEV)')
GROUP BY model_year, electric_vehicle_type
ORDER BY model_year
```

## Installation

1. Copy the `query_enhancer.py` file to your project
2. Apply the patches to `analysis_pg.py`
3. Update the system message for `postgresql_echart_assistant` to include information about using the query enhancer

## Customization

You can customize the Query Enhancer by:

1. **Adjusting the similarity threshold**: Change the `threshold` parameter in `find_best_matches` to make matching more or less strict
2. **Adding more extraction patterns**: Add more regex patterns to `extract_comparison_terms` to handle different query formats
3. **Customizing database connection**: Modify the connection parameters to match your database setup

## Troubleshooting

If you encounter issues:

1. Check the logs for error messages
2. Verify that the database connection parameters are correct
3. Make sure the table and column names are correctly extracted from the query
4. Test the query enhancer with simple examples first

## Conclusion

The Query Enhancer provides a general solution to the problem of mismatches between user query terms and actual database values. By automatically finding the best matches for terms in the database, it ensures that charts are generated with the correct data, even when users don't know the exact names used in the database.
