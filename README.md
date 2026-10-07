# Campus Dynasty: XC

A college cross country coaching game. Inspired by Capus Dynasty, an iOS college basketball coaching simulator.

Pick any Division I program, then run its season: build the meet schedule, plan every day of training, race, and recruit the next class. Teams, runners, and meets are real, loaded from TFRRS data for the 2024 season.

## How it works

1. **Pick a team.** 284 DI programs with their real rosters (about 5,700 runners), ratings, conferences, and regions.
2. **Schedule.** Choose at least 3 regular-season meets from 246, one per week. Conference (week 13), Regionals (week 15), and Nationals (week 16) are added automatically.
3. **Train.** Set each day of the week to an easy day, long run, rest, or a custom interval workout (reps, distance, pace). Harder work builds speed and endurance faster but raises injury risk. Weekly mileage matters too, especially for runners with lower health. Injured runners lose fitness and sit out 1 to 8 weeks.
4. **Race.** Pick 5 to 7 runners and watch the race play out over 8 splits, with places shuffling as it goes. Scoring is standard cross country: top 5 per team, lowest total wins.
5. **Nationals.** The top 31 teams in the rankings qualify. Outside that, a top 6 finish at Regionals gives you a chance at an at-large bid.
6. **Recruit.** Season results earn recruiting points. Spend them over 3 rounds of offers to 150 recruits. Commitment odds depend on the offer, the recruit's rating, and your team's rating. Then seniors graduate and the next season starts.

## Repo layout

```
app.py          Everything: data loading, training and injury model, race sim, recruiting, routes
templates/      Pages
Teams.csv       Programs: name, colors, logo, rating, conference, region
Runners.csv     Athletes: name, team, class, rating
Meets.csv       Regular-season meets: name, date, importance
```

## Usage

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. Set `PORT` to change the port. The `Procfile` runs the same command for Heroku-style hosts.

## Limitations

- All game state is in memory. Restarting the server wipes every save.
- Advancing past week 1 currently crashes, and races don't start. Some of the game logic still uses one shared game state while the pages use a per-player one, so the two don't line up.
- Teams and runners are shared between players. One person's training and recruiting changes the league for everyone on the server.
- The `names` package used for recruit names doesn't install on newer Python versions.
