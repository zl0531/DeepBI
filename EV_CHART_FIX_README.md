# Electric Vehicle Chart Fix

This document provides instructions for diagnosing and fixing the issue with empty charts when comparing Battery Electric Vehicle (BEV) and Plug-in Hybrid Electric Vehicle (PHEV) sales trends.

## Problem Description

When users request a chart comparing BEV and PHEV sales trends, the system successfully generates a chart but it contains no data points. The chart shows empty series:

```json
[{
  'echart_name': 'BEV和PHEV销量趋势比较', 
  'series': [
    {'type': 'bar', 'name': 'BEV', 'data': []}, 
    {'type': 'bar', 'name': 'PHEV', 'data': []}
  ], 
  'xAxis_data': []
}]
```

## Root Causes

The issue could be due to one of the following reasons:

1. **Database Connection Issues**: The connection parameters might be incorrect or the database might not be accessible.
2. **Missing or Empty Data**: The `electric_vehicles` table might not have any records with `electric_vehicle_type` values of 'BEV' or 'PHEV'.
3. **TERMINATE Message Handling**: The system might be incorrectly handling "TERMINATE" messages, causing the final response to be empty.

## Solution

We've implemented several fixes to address these issues:

1. **Improved Error Handling**: The system now properly handles empty data and provides informative messages to users.
2. **Enhanced Chart Generation**: Charts now include a title indicating when no data is available.
3. **Fixed TERMINATE Message Handling**: The system now correctly processes messages without being affected by "TERMINATE" strings.

## Diagnostic Tools

We've provided several scripts to help diagnose and fix the issue:

### 1. Database Verification Script

The `verify_ev_data.py` script checks if the database connection is working and if there's data in the `electric_vehicles` table:

```bash
python verify_ev_data.py
```

This script will:
- Test the database connection
- Check if the `electric_vehicles` table exists
- Count the total records in the table
- Check for BEV and PHEV records
- Display sample data from the table

### 2. Improved Chart Generator

The `improved_ev_chart_generator.py` script generates a chart with robust error handling and fallback to sample data:

```bash
python improved_ev_chart_generator.py
```

To use sample data instead of querying the database:

```bash
python improved_ev_chart_generator.py --sample
```

### 3. Sample Data Generator

If the database doesn't have any BEV or PHEV records, you can use the `generate_ev_sample_data.py` script to populate it with sample data:

```bash
python generate_ev_sample_data.py --records 1000 --start-year 2018 --end-year 2023
```

To clear existing data before inserting new records:

```bash
python generate_ev_sample_data.py --records 1000 --clear
```

## Code Changes

We've made the following changes to the codebase:

1. **analysis_pg.py**:
   - Added detection of empty chart data
   - Added informative titles to charts with no data
   - Improved the analyst prompt to explain possible reasons for missing data
   - Enhanced TERMINATE message handling

2. **New Scripts**:
   - `verify_ev_data.py`: For database verification
   - `improved_ev_chart_generator.py`: For robust chart generation
   - `generate_ev_sample_data.py`: For populating the database with sample data

## Testing the Fix

To test the fix:

1. Run the verification script to check the database:
   ```bash
   python verify_ev_data.py
   ```

2. If no BEV or PHEV data is found, populate the database with sample data:
   ```bash
   python generate_ev_sample_data.py --records 1000 --clear
   ```

3. Test the chart generation:
   ```bash
   python improved_ev_chart_generator.py
   ```

4. Restart the DeepBI service to apply the code changes:
   ```bash
   # Restart the service (command may vary depending on your setup)
   docker-compose restart
   ```

5. Test the chart generation through the DeepBI interface by asking for a comparison of BEV and PHEV sales trends.

## Troubleshooting

If you still encounter issues:

1. Check the logs for any error messages:
   ```bash
   docker-compose logs -f
   ```

2. Verify that the database connection parameters are correct in the scripts and in the DeepBI configuration.

3. Make sure the `electric_vehicles` table has the expected structure and contains data with the correct vehicle types.

4. If using sample data doesn't work, there might be an issue with the chart rendering component. Check the browser console for any JavaScript errors.

## Contact

If you need further assistance, please contact the DeepBI support team.
