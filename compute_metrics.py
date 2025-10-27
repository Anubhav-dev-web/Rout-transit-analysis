import pandas as pd
from datetime import datetime, time
import json

# Paths (same folder)
RIDERSHIP = 'd:/DataAnalyst/PowerBI/Project Data/Transportation/modified_ridership.csv'
ROUTES = 'd:/DataAnalyst/PowerBI/Project Data/Transportation/modified_routes.csv'
BUSES = 'd:/DataAnalyst/PowerBI/Project Data/Transportation/modified_buses.csv'
DEMOS = 'd:/DataAnalyst/PowerBI/Project Data/Transportation/modified_demographics.csv'

# Read CSVs
r = pd.read_csv(RIDERSHIP, parse_dates=['Date'])
routes = pd.read_csv(ROUTES)
buses = pd.read_csv(BUSES)
d = pd.read_csv(DEMOS)

# Normalise time column to datetime.time
r['Time_parsed'] = pd.to_datetime(r['Time'], format='%H:%M', errors='coerce').dt.time

# Join bus -> route
buses_sub = buses[['BusID','RouteID','Capacity']]
merged = r.merge(buses_sub, on='BusID', how='left')
merged = merged.merge(routes[['RouteID','RouteName','TakeOffTime','ArrivalTime']], on='RouteID', how='left')

# Total riders
total_riders = int(merged['NumberOfRiders'].sum())

# Average riders per trip
avg_riders_per_trip = merged['NumberOfRiders'].mean()

# Peak and down hour of operation (most/least frequent Time values)
time_counts = merged['Time'].value_counts().sort_values(ascending=False)
peak_time = time_counts.index[0] if len(time_counts)>0 else None
peak_count = int(time_counts.iloc[0]) if len(time_counts)>0 else 0
# For down time choose least frequent among times that appear (could be many with 1)
down_time = time_counts.index[-1] if len(time_counts)>0 else None
down_count = int(time_counts.iloc[-1]) if len(time_counts)>0 else 0

# Trip time trend: compute route duration (from routes) and average by year using trip rows (use route durations)
# Parse TakeOff and Arrival time as times and compute duration in minutes, handling wrap-around days

def parse_t(t):
    try:
        return datetime.strptime(t, '%H:%M:%S').time()
    except Exception:
        return None

routes['TakeOff_parsed'] = routes['TakeOffTime'].apply(parse_t)
routes['Arrival_parsed'] = routes['ArrivalTime'].apply(parse_t)

from datetime import datetime, timedelta

def duration_minutes(row):
    a = row['TakeOff_parsed']
    b = row['Arrival_parsed']
    if pd.isna(a) or pd.isna(b):
        return None
    dt_a = datetime.combine(datetime(2000,1,1), a)
    dt_b = datetime.combine(datetime(2000,1,1), b)
    if dt_b < dt_a:
        dt_b += timedelta(days=1)
    return (dt_b - dt_a).total_seconds()/60.0

routes['RouteDurationMin'] = routes.apply(duration_minutes, axis=1)

merged = merged.merge(routes[['RouteID','RouteDurationMin']], on='RouteID', how='left')
merged['Year'] = merged['Date'].dt.year

avg_duration_by_year = merged.groupby('Year')['RouteDurationMin'].mean().dropna()
trip_time_trend = None
if 2023 in avg_duration_by_year.index and 2024 in avg_duration_by_year.index:
    v2023 = avg_duration_by_year.loc[2023]
    v2024 = avg_duration_by_year.loc[2024]
    trip_time_trend = ((v2024 - v2023)/v2023)*100
elif len(avg_duration_by_year)>=2:
    years = sorted(avg_duration_by_year.index)
    v1 = avg_duration_by_year.loc[years[-2]]
    v2 = avg_duration_by_year.loc[years[-1]]
    trip_time_trend = ((v2 - v1)/v1)*100

# Route performance (busiest / least busiest)
riders_by_route = merged.groupby('RouteName')['NumberOfRiders'].sum().sort_values(ascending=False)
busiest_route = riders_by_route.index[0] if len(riders_by_route)>0 else None
least_busiest_route = riders_by_route.index[-1] if len(riders_by_route)>0 else None

# Time-range distribution
# bins: 06:00-08:59, 09:00-11:59, 12:00-14:59, 15:00-17:59, 18:00-20:59, 21:00-23:59

def time_to_minutes(tstr):
    try:
        t = datetime.strptime(tstr, '%H:%M').time()
        return t.hour*60 + t.minute
    except Exception:
        return None

merged['TimeMinutes'] = merged['Time'].apply(lambda x: time_to_minutes(x))

bins = [0, 6*60-1, 8*60+59, 11*60+59, 14*60+59, 17*60+59, 20*60+59, 23*60+59]
# but above is messy; we'll define named ranges
ranges = [
    ('6:00 AM - 8:59 AM', 6*60, 8*60+59),
    ('9:00 AM - 11:59 AM', 9*60, 11*60+59),
    ('12:00 PM - 2:59 PM', 12*60, 14*60+59),
    ('3:00 PM - 5:59 PM', 15*60, 17*60+59),
    ('6:00 PM - 8:59 PM', 18*60, 20*60+59),
    ('9:00 PM - 11:59 PM', 21*60, 23*60+59)
]

dist = {}
for label, start, end in ranges:
    mask = merged['TimeMinutes'].between(start, end)
    dist[label] = int(merged.loc[mask, 'NumberOfRiders'].sum())

# Hourly pattern (by hour of day)
merged['Hour'] = merged['TimeMinutes'].apply(lambda x: int(x//60) if pd.notna(x) else None)
hourly = merged.groupby('Hour')['NumberOfRiders'].sum().sort_index()

# Utilization status: under <50% capacity, proper 50%-100% inclusive, over >100%
merged['Capacity'] = merged['Capacity'].fillna(0)
merged['UtilPercent'] = merged['NumberOfRiders'] / merged['Capacity']

under = merged[merged['UtilPercent'] < 0.5].shape[0]
proper = merged[(merged['UtilPercent'] >= 0.5) & (merged['UtilPercent'] <= 1.0)].shape[0]
over = merged[merged['UtilPercent'] > 1.0].shape[0]

# Daily ridership by weekday
merged['Weekday'] = merged['Date'].dt.day_name()
by_weekday = merged.groupby('Weekday')['NumberOfRiders'].sum()
# To present in order Mon-Sun
order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
by_weekday = by_weekday.reindex(order).fillna(0).astype(int)

# Yearly comparison
by_year = merged.groupby('Year')['NumberOfRiders'].sum()
by_year_percent = (by_year / by_year.sum() * 100).round(2)

# Monthly trend
merged['Month'] = merged['Date'].dt.month
by_month = merged.groupby('Month')['NumberOfRiders'].sum().reindex(range(1,13), fill_value=0)

# Filters available
filters = {
    'Voyage Line':'RouteName (from routes)',
    'City Transit':'RouteName (same)',
    'Gender Filter':'available in demographics (Gender via RiderID)',
    'Route Filter':'RouteName'
}

# Build summary
summary = {
    'TotalRiders': total_riders,
    'AverageRidersPerTrip': round(avg_riders_per_trip,2),
    'PeakTime': {'Time': peak_time, 'Occurrences': peak_count},
    'DownTime': {'Time': down_time, 'Occurrences': down_count},
    'TripTimeTrendPercent': round(trip_time_trend,2) if trip_time_trend is not None else None,
    'BusiestRoute': busiest_route,
    'LeastBusiestRoute': least_busiest_route,
    'TimeRangeDistribution': dist,
    'HourlyPattern': hourly.fillna(0).to_dict(),
    'Utilization': {'ProperlyUtilized': int(proper), 'Overutilized': int(over), 'Underutilized': int(under)},
    'DailyRidershipByWeekday': by_weekday.to_dict(),
    'Yearly': {'Totals': by_year.to_dict(), 'Percent': by_year_percent.to_dict()},
    'MonthlyTrend': by_month.to_dict(),
    'FiltersAvailable': filters
}

print('\n--- Human-readable summary ---\n')
print(f"Total Riders (Passengers): {summary['TotalRiders']}")
print(f"Average Riders per Trip: {summary['AverageRidersPerTrip']}")
pt = summary['PeakTime']
print(f"Peak Hour of Operation: {pt['Time']} ({pt['Occurrences']} occurrences)")
dt = summary['DownTime']
print(f"Down Hour of Operation: {dt['Time']} ({dt['Occurrences']} occurrences)")
if summary['TripTimeTrendPercent'] is not None:
    trend = summary['TripTimeTrendPercent']
    arrow = '🔻' if trend<0 else '🔺' if trend>0 else ''
    print(f"Trip Time Trend: {abs(trend):.2f}% {arrow} ({'decrease' if trend<0 else 'increase' if trend>0 else 'no change'})")

print('\nBusiest Route:', summary['BusiestRoute'])
print('Least Busiest Route:', summary['LeastBusiestRoute'])

print('\nTime-Range Distribution:')
for k,v in summary['TimeRangeDistribution'].items():
    print(f"- {k}: {v} riders")

print('\nUtilization Status:', summary['Utilization'])

print('\nDaily Ridership (by Day of Week):')
for k,v in summary['DailyRidershipByWeekday'].items():
    print(f"- {k}: {v} riders")

print('\nYearly Comparison:')
for y,val in summary['Yearly']['Totals'].items():
    # Year keys in Percent dict may be strings or ints depending on pandas version; handle both
    y_int = int(y)
    pct = None
    # try string key first, then int key, then fallback to 0
    pct_dict = summary['Yearly']['Percent']
    if str(y_int) in pct_dict:
        pct = pct_dict[str(y_int)]
    elif y_int in pct_dict:
        pct = pct_dict[y_int]
    else:
        pct = 0
    print(f"- {y_int}: {int(val)} riders ({pct}%)")

# print JSON
print('\n--- JSON output ---')
print(json.dumps(summary, indent=2, default=int))
