# DSCI 560 - Lab 7
Team: Stay Alive

## Project Overview

In this lab, we built a mobile phone-based IoT system using OwnTracks and ThingsBoard.

We deployed ThingsBoard Community Edition on an AWS EC2 Ubuntu instance and connected our phones to it using HTTP telemetry. GPS data (lat/lon) is stored in PostgreSQL and visualized on dashboards in real time.

Instead of only showing basic map tracking, we extended the system into two modules:

1. Fitness tracking
2. AI location recommendation

Both modules use the same GPS telemetry stream.

---

## System Architecture

OwnTracks (mobile GPS)  
→ HTTP  
→ ThingsBoard Rule Chain  
→ PostgreSQL  
→ Dashboard / Extensions

All telemetry first goes into the root rule chain. Before the default "Save Timeseries" node, we inserted additional rule chains to support different applications.

---

## Fitness Extension

This module tracks daily walking activity.

It:
- Computes distance between GPS points
- Filters unrealistic jumps (to reduce GPS drift)
- Calculates calories burned based on user weight
- Displays routes and leaderboard on dashboard

We used the Haversine formula to compute distance in kilometers.

To avoid GPS spikes:
- We applied a threshold filter within a 10-second window
- Distances that are too large are gated out
- Only valid distances contribute to calorie calculation

Calorie formula:
calories = distance_km × weightKG × 0.75

The dashboard shows:
- Real-time walking routes
- Leaderboard ranking
- Total calories burned

We tested this with multiple devices at the same time.

---

## AI Recommendation Extension

This module provides nearby POI recommendations.

When the phone sends a message containing a `poi` field:
- The system captures the GPS coordinates
- Builds a structured prompt
- Sends it to OpenAI through ThingsBoard AI node
- Saves the response
- Pushes recommendations to a Telegram bot

The prompt is structured to:
- Only return real locations
- Limit to 5 results
- No extra conversation text

This module runs on the same telemetry pipeline as the fitness module.

---

## Notes

- The system runs on AWS EC2
- PostgreSQL is used as the ThingsBoard backend
- Multi-device tracking was verified
- EC2 should be stopped after testing to avoid extra charges