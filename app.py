from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import pandas as pd
import random, math, datetime
import copy
import names
import json
from flask import session
import uuid
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key

# ========================
# Load CSV Data
# ========================
teams_df = pd.read_csv("Teams.csv")
runners_df = pd.read_csv("Runners.csv")
meets_df = pd.read_csv("Meets.csv")  # Contains regular-season meets


# ========================
# Define Classes
# ========================
class Athlete:
    def __init__(self, firstname, lastname, team, overall, year_class):
        self.firstname = firstname
        self.lastname = lastname
        self.team = team
        self.overall = float(overall)
        self.year_class = year_class  # 'FR', 'SO', 'JR', or 'SR'
        # Set health based on class.
        if year_class == 'FR':
            self.health = random.randint(50, 70)
        elif year_class == 'SO':
            self.health = random.randint(65, 80)
        elif year_class == 'JR':
            self.health = random.randint(75, 90)
        elif year_class == 'SR':
            self.health = random.randint(80, 95)
        else:
            self.health = random.randint(70, 85)
        self.injury_risk = 5
        self.is_injured = False
        self.recovery_weeks = 0
        self.injury_status = "Healthy"
        self.mileage = 70  # Default mileage.
        self.speed = self.overall
        self.endurance = self.overall

    @property
    def full_name(self):
        return f"{self.firstname} {self.lastname}"

    def improve_stats(self, speed_improvement, endurance_improvement):
        speed_factor = math.exp(-self.speed / 10)
        random_factor_speed = random.uniform(0.9, 1.1)
        improvement_speed = speed_improvement * speed_factor * random_factor_speed

        endurance_factor = math.exp(-self.endurance / 10)
        random_factor_endurance = random.uniform(0.9, 1.1)
        improvement_endurance = endurance_improvement * endurance_factor * random_factor_endurance

        self.speed += improvement_speed
        self.endurance += improvement_endurance

        self.speed = min(99, self.speed)
        self.endurance = min(99, self.endurance)

        self.overall = 0.85 * self.endurance + 0.15 * self.speed
        if self.lastname == 'Mann':
            self.overall += 10
        self.overall = min(99, self.overall)
        self.overall = round(self.overall, 2)


class Team:
    def __init__(self, team, color, logo, overall, conference, region):
        self.team = team
        self.color = color
        self.logo = logo
        self.overall = round(overall, 2)
        self.conference = conference
        self.region = region
        self.athletes = []


class Meet:
    def __init__(self, name, date, importance):
        self.name = name
        # For regular-season meets, date comes from CSV; for postseason, we'll set a fixed week.
        if date:
            self.date_obj = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            season_start = datetime.date(2024, 8, 30)
            computed_week = ((self.date_obj - season_start).days // 7) + 1
            self.week = max(1, computed_week)
        else:
            # For postseason, we'll set week manually.
            self.week = None
        self.importance = round(importance, 2) if importance is not None else None
        self.capacity = int(round(((self.importance - 1) / 9) * (20 - 5) + 1)) if self.importance else None
        self.competitors = []


# ========================
# Load Data into Objects
# ========================
teams = {}
for idx, row in teams_df.iterrows():
    overall = float(row['overall'])
    if overall == 'N/A':
        overall = 0

    t = Team(
        team=row['team'],
        color=row['color'],
        logo=row['logo'],
        overall=overall,
        conference=row['conference'],
        region=row['region']
    )
    teams[t.team] = t


for idx, row in runners_df.iterrows():
    athlete = Athlete(
        firstname=row['firstname'],
        lastname=row['lastname'],
        team=row['team'],
        overall=row['overall'],
        year_class=row['class']
    )
    if athlete.team in teams:
        teams[athlete.team].athletes.append(athlete)

# Load regular-season meets from CSV.
regular_meets = []
for idx, row in meets_df.iterrows():
    m = Meet(
        name=row['name'],
        date=row['date'],
        importance=row['importance']
    )
    if row['importance'] > 2:
        regular_meets.append(m)

# ========================
# Global Game State
# ========================
game_state = {
    "player_team": None,
    "current_week": 1,
    "total_weeks": 16,
    "scheduled_meets": [],  # Will include regular-season meets (user-chosen) plus mandatory postseason meets.
    "training_plan": {},  # Key: week number -> dict(day -> activity)
    "race_results": {},  # Key: week -> race result data
    "race_simulation": {}  # For live race simulation state.
}

# Global dictionary to store each user’s game state.
user_game_states = {}

def get_game_state():
    # Ensure each user gets a unique id stored in the session.
    if "game_state_id" not in session:
        session["game_state_id"] = str(uuid.uuid4())
    game_state_id = session["game_state_id"]
    # If there is no game state for this ID, initialize one.
    if game_state_id not in user_game_states:
        user_game_states[game_state_id] = {
            "player_team": None,
            "current_week": 1,
            "total_weeks": 16,
            "scheduled_meets": [],
            "training_plan": {},
            "race_results": {},
            "race_simulation": {},
            # Add any additional keys you need (e.g., recruiting data).
            "recruits": None,
            "recruiting_round": None,
            "recruiting_points": None,
        }
    return user_game_states[game_state_id]

# ------------------------
# Append Mandatory Postseason Meets
# ------------------------
def setup_postseason():
    # Create three mandatory meets:
    # Conference Championship in Week 13,
    # Regional Championship in Week 15,
    # National Championship in Week 16.

    # Conference Championship: Only teams in the same conference as the player's team.
    conf_meet = Meet(name="Conference Championship", date=None, importance=9)
    conf_meet.week = 13
    # Regional Championship: Only teams in the same region.
    reg_meet = Meet(name="Regional Championship", date=None, importance=9)
    reg_meet.week = 15
    # National Championship: Top 31 teams nationally.
    nat_meet = Meet(name="National Championship", date=None, importance=10)
    nat_meet.week = 16

    # For Conference and Regional meets, we'll filter teams based on player's team.
    if game_state.get("player_team"):
        player = game_state["player_team"]
        conf_meet.competitors = [t for t in teams.values() if
                                 t.conference == player.conference and t.team != player.team]
        # Include player's team automatically.
        conf_meet.competitors.append(player)
        # For regionals, filter by region.
        reg_meet.competitors = [t for t in teams.values() if t.region == player.region and t.team != player.team]
        reg_meet.competitors.append(player)
    else:
        conf_meet.competitors = []
        reg_meet.competitors = []
    # For National Championship, select top 31 nationally.
    all_teams_sorted = sorted(teams.values(), key=lambda t: t.overall, reverse=True)
    nat_meet.competitors = all_teams_sorted[:31]

    # Append these postseason meets to the scheduled_meets.
    game_state["scheduled_meets"].extend([conf_meet, reg_meet, nat_meet])


# ------------------------
# Competitor Assignment for Regular Meets
# ------------------------
def assign_competitors_to_meets():
    # For each regular meet, clear competitors and assign using your algorithm.
    for m in regular_meets:
        m.competitors = []
    sorted_teams = sorted(teams.values(), key=lambda t: t.overall, reverse=True)
    for team in sorted_teams:
        if game_state.get("player_team") and team.team == game_state["player_team"].team:
            continue
        meet_amount = random.randint(3, 6)
        assigned_weeks = set()
        # Use regular meets only.
        sorted_meets = sorted(regular_meets, key=lambda m: m.importance, reverse=True)
        for meet in sorted_meets:
            if len(meet.competitors) < meet.capacity and (meet.week not in assigned_weeks):
                if random.random() < 0.9:
                    meet.competitors.append(team)
                    assigned_weeks.add(meet.week)
                    meet_amount -= 1
                    if meet_amount <= 0:
                        break


# Pre-assign competitors for regular meets.
assign_competitors_to_meets()


# ------------------------
# Combine Regular Meets and Postseason
# ------------------------
def combine_schedule():
    # Assume the user has chosen a list of regular meets.
    # For simplicity, let’s assume game_state["scheduled_meets"] already contains the chosen regular meets.
    # Now, append mandatory postseason meets.
    setup_postseason()


# For now, if the user hasn't finalized their schedule, game_state["scheduled_meets"] will be set later.
# When the schedule is finalized by the user, you can call combine_schedule().

# ------------------------
# Race Simulator Functions (unchanged from earlier, with final split storing results)
# ------------------------
def init_race_simulation(meet_name):
    meet = next((m for m in game_state["scheduled_meets"] if m.name == meet_name), None)
    if not meet:
        return
    race_field = []
    for team in meet.competitors:
        sorted_ath = sorted(team.athletes, key=lambda a: a.overall, reverse=True)[:7]
        for a in sorted_ath:
            race_field.append({
                "id": f"{team.team}_{a.full_name}",
                "name": a.full_name,
                "team": team.team,
                "overall": a.overall,
                "current_performance": a.overall
            })
    player_team = game_state["player_team"]
    if "race_roster" in game_state:
        roster = game_state["race_roster"]
    else:
        roster = sorted(player_team.athletes, key=lambda a: a.overall, reverse=True)[:7]
    for a in roster:
        race_field.append({
            "id": f"{player_team.team}_{a.full_name}",
            "name": a.full_name,
            "team": player_team.team,
            "overall": a.overall,
            "current_performance": a.overall
        })
    race_field.sort(key=lambda r: r["current_performance"], reverse=True)
    game_state["race_simulation"][meet_name] = {
        "field": race_field,
        "previous_order": [r["id"] for r in race_field],
        "current_split": 0,
        "started": False
    }


def simulate_split(meet_name, split):
    sim = game_state["race_simulation"].get(meet_name)
    if not sim:
        return {"error": "No simulation found."}
    field = sim["field"]
    prev_order = sim["previous_order"]
    rand_range = 5 - (split - 1) * (4 / 7)
    for runner in field:
        runner["current_performance"] = runner["overall"] + random.uniform(-rand_range, rand_range)
    field.sort(key=lambda r: r["current_performance"], reverse=True)
    new_order = [r["id"] for r in field]
    changes = {}
    for rid in new_order:
        prev_idx = prev_order.index(rid) if rid in prev_order else 0
        curr_idx = new_order.index(rid)
        changes[rid] = prev_idx - curr_idx
    sim["previous_order"] = new_order
    sim["current_split"] = split
    individual_results = []
    for i, runner in enumerate(field):
        individual_results.append({
            "place": i + 1,
            "name": runner["name"],
            "team": runner["team"],
            "change": changes.get(runner["id"], 0)
        })
    team_map = {}
    for r in individual_results:
        team_map.setdefault(r["team"], []).append(r)
    scoring_list = []
    for t, runners in team_map.items():
        scoring_list.extend(runners[:5])
    scoring_list.sort(key=lambda r: r["place"])
    team_results = {t: 0 for t in team_map}
    for idx, r in enumerate(scoring_list):
        points = idx + 1
        r["points"] = points
        team_results[r["team"]] += points
    for t, runners in team_map.items():
        if len(runners) > 5:
            for r in runners[5:]:
                r["points"] = ""
    final = (split == 8)
    data = {
        "split": split,
        "individual_results": individual_results,
        "team_results": team_results,
        "final": final
    }
    if final:
        sorted_teams = sorted(team_results.items(), key=lambda x: x[1])
        total_teams = len(sorted_teams)
        player_team_name = game_state["player_team"].team
        player_position = None
        for rank, (tname, pts) in enumerate(sorted_teams, start=1):
            if tname == player_team_name:
                player_position = rank
                break
        data["player_position"] = player_position
        data["total_teams"] = total_teams
        cw = game_state["current_week"]
        game_state["race_results"][cw] = data
    return data


# ------------------------
# Training Simulation Functions (same as before, with no changes for injury handling)
# ------------------------
def apply_training_effects(athlete, training_plan):
    speed_coefficient = 0.2
    strength_coefficient = 0.1
    injury_coefficient = 10
    interval_amount_exp = 1
    pace_exp = 5
    total_injury_risk = 0

    speed_improvement = 0
    endurance_improvement = 0

    for day, activity in training_plan.items():
        if isinstance(activity, str):
            act = activity.strip().lower()
        else:
            act = None
        if act == "easy day":
            endurance_improvement += 0.01
            total_injury_risk -= 0.1
        elif act == "long run":
            endurance_improvement += strength_coefficient * 1.5
            total_injury_risk += 0.5
        elif act == "race":
            total_injury_risk += 2
        elif act == "rest":
            total_injury_risk -= 0.5
        elif isinstance(activity, dict) and activity.get("Type") == "Workout":
            il = activity.get("Interval Length")
            ia = activity.get("Interval Amount")
            pf = activity.get("Pace Factor")
            total_distance = il * ia
            speed_improvement += speed_coefficient * (pf ** 2) * total_distance
            endurance_improvement += strength_coefficient * (1 + pf) * total_distance
            injury_risk = injury_coefficient * total_distance * ((1 / ia) ** interval_amount_exp) * (pf ** pace_exp)
            total_injury_risk += injury_risk
        else:
            print(f"Unrecognized activity '{activity}' on {day}")
    mileage_strength = (athlete.mileage / 100) * (strength_coefficient * 0.5)
    mileage_risk = injury_coefficient * ((athlete.mileage - 50) / 50) * ((100 - athlete.health) / 100)
    total_injury_risk += mileage_risk

    decay = 0.9
    athlete.injury_risk *= decay
    athlete.injury_risk = max(0, athlete.injury_risk + total_injury_risk)

    if athlete.injury_risk >= 15:
        athlete.is_injured = True
        athlete.recovery_weeks = random.choices(range(1, 9), weights=[8, 7, 6, 5, 4, 3, 2, 1])[0]
        athlete.injury_status = "Injured"
        damage = random.randint(5, 10)
        athlete.health = max(0, athlete.health - damage)
    else:
        if athlete.injury_risk < 5:
            athlete.injury_status = "Healthy"
        elif athlete.injury_risk < 10:
            athlete.injury_status = "Questionable"
        else:
            athlete.injury_status = "Doubtful"
    if athlete.injury_status != "Injured":
        athlete.improve_stats(speed_improvement, endurance_improvement)
        athlete.improve_stats(0, mileage_strength)


def update_athletes():
    cw = game_state["current_week"]
    plan = game_state["training_plan"].get(cw, {})
    status_changes = []
    for athlete in game_state["player_team"].athletes:
        prev = athlete.injury_status
        if athlete.is_injured:
            athlete.endurance = max(0, athlete.endurance - 0.5)
            athlete.speed = max(0, athlete.speed - 0.5)
            athlete.recovery_weeks -= 1
            if athlete.recovery_weeks <= 0:
                athlete.is_injured = False
                athlete.injury_status = "Healthy"
                athlete.injury_risk = 0
                status_changes.append(f"{athlete.full_name} has recovered from injury!")
        else:
            orig_speed = athlete.speed
            orig_endurance = athlete.endurance
            apply_training_effects(athlete, plan)
            if athlete.is_injured:
                athlete.speed = orig_speed
                athlete.endurance = orig_endurance
        if athlete.injury_status != prev:
            if athlete.is_injured:
                status_changes.append(
                    f"{athlete.full_name}'s injury status changed to Injured ({athlete.recovery_weeks} Week{'s' if athlete.recovery_weeks != 1 else ''} Recovery).")
            else:
                status_changes.append(f"{athlete.full_name}'s injury status changed to {athlete.injury_status}.")
    return status_changes


# ------------------------
# Standard Routes
# ------------------------
@app.route('/')
def index():
    return render_template("index.html")


@app.route('/select_team', methods=['GET', 'POST'])
def select_team():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))
    query = request.args.get("q", "")
    if query:
        filtered = [t for t in teams.values() if query.lower() in t.team.lower()]
    else:
        filtered = list(teams.values())
    if request.method == "POST":
        team_name = request.form.get("team")
        if team_name in teams:
            game_state["player_team"] = teams[team_name]
            session["player_team"] = team_name
            game_state["current_week"] = 1
            game_state["scheduled_meets"] = []  # Will be set by the schedule route.
            flash(f"You are now coaching {team_name}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid team selection.", "danger")
    return render_template("select_team.html", teams=filtered, query=query)


@app.context_processor
def inject_globals():
    return {
        "player_team": game_state.get("player_team"),
        "scheduled_meets": game_state.get("scheduled_meets", [])
    }


@app.route('/dashboard')
def dashboard():
    state = get_game_state()
    if not state.get("player_team"):
        return redirect(url_for("select_team"))
    cw = state["current_week"]
    plan = state["training_plan"].get(cw, {})
    scheduled_race = next((m for m in state["scheduled_meets"] if m.week == cw), None)
    race_done = (cw in state["race_results"])
    race_result = state["race_results"].get(cw)
    season_over = (cw > state["total_weeks"])
    return render_template("dashboard.html",
                           team=state["player_team"],
                           current_week=cw,
                           total_weeks=state["total_weeks"],
                           training=plan,
                           scheduled_race=scheduled_race,
                           race_done=race_done,
                           race_result=race_result,
                           season_over=season_over,
                           scheduled_meets=state["scheduled_meets"])




@app.route('/roster')
def roster():
    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    return render_template("roster.html", team=game_state["player_team"])


@app.route('/edit_mileage', methods=['GET', 'POST'])
def edit_mileage():
    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    team = game_state["player_team"]
    if request.method == "POST":
        for a in team.athletes:
            val = request.form.get(a.full_name)
            if val:
                try:
                    a.mileage = int(val)
                except:
                    pass
        flash("Mileage updated for all athletes.", "success")
        return redirect(url_for("roster"))
    return render_template("edit_mileage.html", team=team)


@app.route('/schedule', methods=['GET','POST'])
def schedule():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    query = request.args.get("q", "")
    if query:
        filtered_meets = [m for m in regular_meets if query.lower() in m.name.lower()]
    else:
        filtered_meets = regular_meets
    sort_by = request.args.get("sort_by", "week")
    if sort_by == "importance":
        filtered_meets.sort(key=lambda m: m.importance, reverse=True)
    elif sort_by == "alphabetical":
        filtered_meets.sort(key=lambda m: m.name.lower())
    else:
        filtered_meets.sort(key=lambda m: m.week)
    if request.method == "POST":
        selected_names = request.form.getlist("meet")
        chosen = [m for m in filtered_meets if m.name in selected_names]
        if len(chosen) < 3:
            flash("Please schedule at least 3 meets.", "danger")
        else:
            wks = [m.week for m in chosen]
            if len(wks) != len(set(wks)):
                flash("You cannot schedule two meets in the same week!", "danger")
            else:
                game_state["scheduled_meets"] = chosen
                # Append mandatory postseason meets.
                setup_postseason()
                flash("Meet schedule finalized!", "success")
                return redirect(url_for("dashboard"))
    return render_template("schedule.html", meets=filtered_meets, query=query, sort_by=sort_by)



@app.route('/view_schedule')
def view_schedule():
    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    return render_template("view_schedule.html",
                           scheduled=game_state["scheduled_meets"],
                           race_results=game_state["race_results"])


@app.route('/training', methods=['GET', 'POST'])
def training():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    if not game_state.get("scheduled_meets"):
        flash("You must finalize your schedule before setting your training plan.", "danger")
        return redirect(url_for("schedule"))
    cw = game_state["current_week"]
    plan = game_state["training_plan"].get(cw, {})
    scheduled_race = next((m for m in game_state["scheduled_meets"] if m.week == cw), None)
    if request.method == "POST":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days:
            if day == "Friday" and scheduled_race:
                plan[day] = "Race"
            else:
                sel = request.form.get(day)
                if sel == "Workout":
                    try:
                        ia = request.form.get(f"interval_amount_{day}")
                        il = request.form.get(f"interval_length_{day}")
                        ps = request.form.get(f"pace_{day}")
                        if not (ia and il and ps):
                            flash(f"You must fill all workout details for {day}.", "danger")
                            return redirect(url_for("training"))
                        ia = int(ia)
                        il = float(il)
                        parts = ps.split(":")
                        if len(parts) == 2:
                            mins = int(parts[0])
                            secs = int(parts[1])
                            tot = mins * 60 + secs
                        else:
                            tot = 300
                        pf = (360 - tot) / 120.0
                        pf = max(0, min(1, pf))
                        wkt = {
                            "Type": "Workout",
                            "Interval Amount": ia,
                            "Interval Length": il,
                            "Pace": ps,
                            "Pace Factor": pf
                        }
                        plan[day] = wkt
                    except Exception as e:
                        flash(f"Error in workout for {day}: {e}", "danger")
                        return redirect(url_for("training"))
                else:
                    plan[day] = sel
        game_state["training_plan"][cw] = plan
        flash("Training plan submitted!", "success")
        return redirect(url_for("dashboard"))
    return render_template("training.html", week=cw, training=plan, scheduled_race=scheduled_race)


@app.route('/design_workout/<day>', methods=['GET', 'POST'])
def design_workout(day):
    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    cw = game_state["current_week"]
    if request.method == "POST":
        try:
            ia = int(request.form.get("interval_amount"))
            il = float(request.form.get("interval_length"))
            ps = request.form.get("pace")
            parts = ps.split(":")
            if len(parts) == 2:
                mins = int(parts[0])
                secs = int(parts[1])
                tot = mins * 60 + secs
            else:
                tot = 300
            pf = (360 - tot) / 120.0
            pf = max(0, min(1, pf))
            wkt = {
                "Type": "Workout",
                "Interval Amount": ia,
                "Interval Length": il,
                "Pace": ps,
                "Pace Factor": pf
            }
            game_state["training_plan"].setdefault(cw, {})[day] = wkt
            flash(f"Workout for {day} saved.", "success")
            return redirect(url_for("training"))
        except Exception as e:
            flash(f"Error in designing workout: {e}", "danger")
    return render_template("design_workout.html", day=day)


@app.route('/next_week')
def next_week():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    if not game_state.get("player_team"):
        return redirect(url_for("select_team"))
    cw = game_state["current_week"]

    # If current week is 17, season is over. Redirect to Season Review.
    if cw == 17:
        flash("Season complete! Proceed to Season Review.", "info")
        return redirect(url_for("season_review"))

    # Block progression if a race is scheduled for this week but the result is not yet recorded.
    scheduled_race = next((m for m in game_state["scheduled_meets"] if m.week == cw), None)
    if scheduled_race and cw not in game_state["race_results"]:
        flash("You must complete the race for this week before proceeding!", "danger")
        return redirect(url_for("dashboard"))

    # Ensure a training plan for the current week is set.
    if not game_state["training_plan"].get(cw):
        flash(f"You must set the training plan for week {cw} before proceeding.", "danger")
        return redirect(url_for("training"))

    # Update team ratings and athlete statuses.
    update_team_ratings()
    changes = update_athletes()
    for msg in changes:
        flash(msg, "info")

    # Copy current week's training plan to next week.
    next_week_num = cw + 1
    new_plan = copy.deepcopy(game_state["training_plan"][cw])

    # If a race is scheduled this week, next week’s Friday must be "Race".
    if scheduled_race:
        new_plan["Friday"] = "Race"
    else:
        # If no race is scheduled this week but the previous week's Friday was "Race", set it to "Easy Day".
        previous_scheduled_race = next((m for m in game_state["scheduled_meets"] if m.week == cw - 1), None)
        if previous_scheduled_race and game_state["training_plan"].get(cw).get("Friday") == "Race":
            new_plan["Friday"] = "Easy Day"

    game_state["training_plan"][next_week_num] = new_plan

    # Increment the current week.
    game_state["current_week"] += 1
    return redirect(url_for("dashboard"))


def update_team_ratings():
    """
    Update every team's overall rating for the new week.

    - For the player's team, recalculate the overall rating as the average of the top 5 athletes' overall ratings.
    - For all other teams, randomly adjust their overall rating by a value in the range [-0.3, 0.3].
    """
    player_team = game_state.get("player_team")
    # Update player's team overall rating if athletes exist.
    if player_team and player_team.athletes:
        # Get the top 5 athletes based on overall rating.
        top_athletes = sorted(player_team.athletes, key=lambda a: a.overall, reverse=True)[:5]
        if top_athletes:
            new_rating = sum(a.overall for a in top_athletes) / len(top_athletes)
            player_team.overall = new_rating

    # Update every other team's overall rating.
    for team in teams.values():
        # Skip the player's team.
        if player_team and team.team == player_team.team:
            continue
        delta = random.uniform(-0.3, 0.3)
        # Clamp the overall rating between 1 and 99.
        team.overall = max(1, min(99, team.overall + delta))


### Race Simulator Routes ###
@app.route('/race_simulator/<meet_name>', methods=['GET', 'POST'])
def race_simulator(meet_name):
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    if request.method == "POST":
        # Check for Skip Race submission.
        if "skip_race" in request.form:
            cw = game_state["current_week"]
            data = {"final": True, "skipped": True, "player_position": None, "total_teams": 0}
            game_state["race_results"][cw] = data
            flash("You skipped the race this week.", "info")
            return redirect(url_for("dashboard"))
        selected_ids = request.form.getlist("runner")
        pteam = game_state["player_team"]
        final_roster = []
        for a in pteam.athletes:
            ident = f"{pteam.team}_{a.full_name}"
            if ident in selected_ids:
                final_roster.append(a)
        if len(final_roster) < 5:
            flash("You must select at least 5 runners, or choose to skip the race.", "danger")
            return redirect(url_for("race_simulator", meet_name=meet_name))
        final_roster = final_roster[:7]
        game_state["race_roster"] = final_roster
        init_race_simulation(meet_name)
        return redirect(url_for("race_simulator", meet_name=meet_name))
    if meet_name not in game_state["race_simulation"]:
        pteam = game_state["player_team"]
        sorted_ath = sorted(pteam.athletes, key=lambda a: a.overall, reverse=True)[:10]
        return render_template("race_roster_selection.html", roster=sorted_ath, meet_name=meet_name)
    sim = game_state["race_simulation"][meet_name]
    if not sim.get("started"):
        return render_template("race_simulator.html", meet_name=meet_name)
    else:
        return render_template("race_live.html", meet_name=meet_name, simulation=sim)


@app.route('/start_race/<meet_name>', methods=['POST'])
def start_race(meet_name):
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))
    sim = game_state["race_simulation"].get(meet_name)
    if sim:
        sim["started"] = True
        sim["current_split"] = 0
    return redirect(url_for("race_simulator", meet_name=meet_name))


@app.route('/race_split/<meet_name>/<int:split>')
def race_split(meet_name, split):
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    data = simulate_split(meet_name, split)
    return jsonify(data)


@app.route('/rankings')
def rankings():
    ranking = sorted(teams.values(), key=lambda t: t.overall, reverse=True)
    return render_template("rankings.html", ranking=ranking, player_team=game_state["player_team"])


# ------------------------
# Postseason Qualification (for National Championship)
# ------------------------
def check_national_qualification():
    """
    Check if the player's team qualifies for nationals (week 16).
    Qualification rules:
      - If the player's team is ranked in the top 31 nationally, they qualify.
      - Otherwise, if the player's team placed in the top 6 of the regional championship (week 15),
        their chance to qualify is (1 / regional_place) * 2.
      - If the team does not qualify, return False.
    """
    # Get national ranking.
    all_teams_sorted = sorted(teams.values(), key=lambda t: t.overall, reverse=True)
    national_rank = None
    player_team = game_state["player_team"]
    for idx, t in enumerate(all_teams_sorted, start=1):
        if t.team == player_team.team:
            national_rank = idx
            break
    if national_rank is None:
        return False

    if national_rank <= 31:
        return True  # Automatically qualifies.
    # Else, check regional result (week 15).
    regional_result = game_state["race_results"].get(15)
    if regional_result and "player_position" in regional_result:
        if regional_result["player_position"] <= 6:
            chance = (1 / regional_result["player_position"]) * 2
            if random.random() < chance:
                return True
    return False


# Before starting national championship (week 16), check qualification.
@app.route('/start_nationals')
def start_nationals():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    cw = game_state["current_week"]
    if cw != 16:
        flash("Nationals can only be started in week 16.", "danger")
        return redirect(url_for("dashboard"))
    qualifies = check_national_qualification()
    if not qualifies:
        flash("Your team did not qualify for Nationals. Season is over.", "danger")
        # Optionally, you can reset the game or redirect to a season-end page.
        return redirect(url_for("dashboard"))
    # Otherwise, create the national championship meet.
    # For nationals, competitors are the top 31 nationally.
    nat_meet = next((m for m in game_state["scheduled_meets"] if m.name == "National Championship"), None)
    if not nat_meet:
        all_teams_sorted = sorted(teams.values(), key=lambda t: t.overall, reverse=True)
        nat_meet = Meet(name="National Championship", date=None, importance=10)
        nat_meet.week = 16
        nat_meet.competitors = all_teams_sorted[:31]
        game_state["scheduled_meets"].append(nat_meet)
    flash("Nationals starting!", "success")
    return redirect(url_for("race_simulator", meet_name=nat_meet.name))


@app.route('/season_review')
def season_review():
    # Build review for each scheduled meet.
    reviews = []
    for meet in game_state["scheduled_meets"]:
        if meet.week in game_state["race_results"]:
            result = game_state["race_results"][meet.week]
            if result.get("skipped"):
                note = "Race Skipped"
                pts = 0
            else:
                note = f"{result['player_position']}th place"
                pts = calculate_recruiting_points(meet, result["player_position"])
            reviews.append({
                "meet_name": meet.name,
                "note": note,
                "points": pts,
                "meet": meet
            })
    total_points = sum(r["points"] for r in reviews)

    # Build recruiting summary: list only for recruits that had an offer.
    recruiting_summary = []
    if "recruits" in game_state:
        for recruit in game_state["recruits"]:
            if recruit.get("round", 0) > 0 and recruit["offer"] > 0:
                recruiting_summary.append(f"{recruit['name']}: {recruit['status']} (Offer: {recruit['offer']})")

    return render_template("season_review.html", reviews=reviews, total_points=total_points,
                           recruiting_summary=recruiting_summary)

@app.route('/recruiting_summary')
def recruiting_summary():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))
    # Build a list of recruits that committed.
    committed_recruits = [r for r in game_state.get("recruits", []) if r["status"] == "Committed"]
    return render_template("recruiting_summary.html", recruits=committed_recruits)


@app.route('/start_next_season')
def start_next_season():
    state = get_game_state()
    if not state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    # Add committed recruits to player's team as new freshmen.
    player_team = game_state["player_team"]
    if "recruits" in game_state:
        for recruit in game_state["recruits"]:
            if recruit["status"] == "Committed":
                names_list = recruit["name"].split()
                firstname = names_list[0]
                lastname = " ".join(names_list[1:]) if len(names_list) > 1 else ""
                new_athlete = Athlete(firstname, lastname, player_team.team, recruit["overall"], "FR")
                new_athlete.health = random.randint(60, 99)
                player_team.athletes.append(new_athlete)

    # Advance every athlete one class; SR athletes graduate.
    def next_class(cls):
        if cls == "FR": return "SO"
        if cls == "SO": return "JR"
        if cls == "JR": return "SR"
        if cls == "SR": return None
        return cls

    for team in teams.values():
        new_roster = []
        for athlete in team.athletes:
            new_cls = next_class(athlete.year_class)
            if new_cls:
                athlete.year_class = new_cls
                new_roster.append(athlete)
            # Else, athlete graduates.
        team.athletes = new_roster
        # For teams other than the player's, generate 5 new freshmen.
        if team.team != player_team.team:
            new_freshmen = []
            for _ in range(5):
                full_name = names.get_full_name(gender='male')
                overall = team.overall * random.uniform(0.75, 0.95)
                names_list = full_name.split()
                firstname = names_list[0]
                lastname = " ".join(names_list[1:]) if len(names_list) > 1 else ""
                new_athlete = Athlete(firstname, lastname, team.team, overall, "FR")
                new_athlete.health = random.randint(60, 99)
                new_freshmen.append(new_athlete)
            team.athletes.extend(new_freshmen)

    # Reset the season: clear scheduled meets, training plans, race results, recruiting data, etc.
    game_state["current_week"] = 1
    game_state["scheduled_meets"] = []
    game_state["training_plan"] = {}
    game_state["race_results"] = {}
    game_state["race_simulation"] = {}
    if "recruits" in game_state:
        del game_state["recruits"]
    game_state["recruiting_round"] = 1
    update_team_ratings()

    flash("New season started! Your team has been updated.", "success")
    return redirect(url_for("dashboard"))


def calculate_recruiting_points(meet, placement):
    """
    recruiting_points = e^(4 * (importance/10)) * (0.90)^(placement - 1)
    For postseason meets:
      - Conference/Regional: importance = 8
      - Nationals: importance = 10
    For regular meets, use meet.importance if defined.
    """
    if placement is None or placement <= 0:
        return 0
    if meet.name == "National Championship":
        importance = 10
    elif meet.name in ["Conference Championship", "Regional Championship"]:
        importance = 8
    else:
        importance = meet.importance if meet.importance is not None else 5
    points = math.exp(4 * (importance / 10)) * (0.90 ** (placement - 1))
    return points

@app.route('/start_recruiting')
def start_recruiting():
    flash("Recruiting functionality is not yet implemented.", "info")
    return redirect(url_for("dashboard"))


@app.route('/recruiting', methods=['GET', 'POST'])
def recruiting():
    # Ensure player's team is selected.
    if not game_state.get("player_team"):
        flash("You must select a team before recruiting.", "danger")
        return redirect(url_for("select_team"))

    # If recruits haven't been generated, generate 150 recruits.
    if "recruits" not in game_state:
        recruits = []
        for _ in range(150):
            full_name = names.get_full_name(gender='male')
            # Use a triangular distribution so that higher overall ratings are less common.
            overall = random.triangular(40, 85, 40)  # Mode near 40.
            recruit = {
                "name": full_name,
                "overall": overall,
                "status": None,  # None means still available this round.
                "round": 0,  # Recruiting round in which a decision is made.
                "offer": 0.0  # Points offered.
            }
            recruits.append(recruit)
        recruits.sort(key=lambda r: r["overall"], reverse=True)
        game_state["recruits"] = recruits
        game_state["recruiting_round"] = 1
        # Set initial recruiting points (e.g., between 50 and 100; here we use 100 for testing).
        game_state["recruiting_points"] = 100

    current_round = game_state["recruiting_round"]
    remaining_points = game_state["recruiting_points"]

    # GET request: Reset status for recruits that are not committed so they appear in the list.
    if request.method == "GET":
        for recruit in game_state["recruits"]:
            if recruit["status"] != "Committed":
                recruit["status"] = None
        pending_recruits = [r for r in game_state["recruits"] if r["status"] is None]
        return render_template("recruiting.html",
                               recruits=pending_recruits,
                               round=current_round,
                               recruiting_points=remaining_points)

    # POST request: Process the submitted offers or skip the round.
    if request.method == "POST":
        # If "Skip Recruiting Round" button was pressed.
        if "skip_recruiting" in request.form:
            for recruit in game_state["recruits"]:
                if recruit["status"] is None:
                    recruit["status"] = "Declined"
                    recruit["round"] = current_round
            flash(f"You skipped recruiting round {current_round}.", "info")
            game_state["recruiting_round"] += 1
            current_round = game_state["recruiting_round"]
            if current_round > 3:
                flash("Recruiting is complete.", "success")
                return redirect(url_for("recruiting_summary"))
            else:
                return redirect(url_for("recruiting"))

        # Process offers.
        offers = {}
        round_total = 0.0
        for recruit in game_state["recruits"]:
            if recruit["status"] is None:
                offer_str = request.form.get(recruit["name"])
                if offer_str:
                    try:
                        offer_val = float(offer_str)
                        # Only process recruits that received a nonzero offer.
                        if offer_val > 0:
                            offers[recruit["name"]] = offer_val
                            round_total += offer_val
                    except ValueError:
                        continue
        if round_total > remaining_points:
            flash(f"Total offered points ({round_total}) exceed your remaining recruiting points ({remaining_points}).",
                  "danger")
            return redirect(url_for("recruiting"))


        player_team = game_state["player_team"]
        team_overall = player_team.overall  # Assume this is updated.

        def calculate_commitment_chance(recruit, offer):
            # Define required cost: recruit.overall - 35 (so a recruit with overall 40 requires 5 points; overall 85 requires 50).
            required = recruit["overall"] - 35
            base_chance = max(0.1, 1.0 - ((recruit["overall"] - team_overall) / 100))
            final_chance = base_chance * (offer / required)
            return max(0.05, min(final_chance, 0.95))

        round_results = []
        # Process only recruits that received an offer.
        for recruit in game_state["recruits"]:
            if recruit["status"] is None and recruit["name"] in offers:
                offer_val = offers[recruit["name"]]
                chance = calculate_commitment_chance(recruit, offer_val)
                if random.random() < chance:
                    recruit["status"] = "Committed"
                    # Deduct the offered points from the recruiting pool.
                    game_state["recruiting_points"] -= offer_val
                else:
                    recruit["status"] = "Declined"
                recruit["round"] = current_round
                recruit["offer"] = offer_val
                round_results.append(f"{recruit['name']} - {recruit['status']}")
        if round_results:
            flash("Round " + str(current_round) + " results:<br>" + "<br>".join(round_results), "info")

        game_state["recruiting_round"] += 1
        current_round = game_state["recruiting_round"]
        if current_round > 3:
            flash("Recruiting is complete.", "success")
            return redirect(url_for("recruiting_summary"))
        else:
            flash(
                f"Proceeding to Recruiting Round {current_round}. Remaining Recruiting Points: {game_state['recruiting_points']}",
                "info")
            return redirect(url_for("recruiting"))


@app.route('/debug_recruiting')
def debug_recruiting():
    game_state["current_week"] = 17  # Assume season is over.
    game_state["recruiting_round"] = 1
    game_state["recruiting_points"] = 100
    if "recruits" in game_state:
        del game_state["recruits"]
    flash("DEBUG: Recruiting reset. Starting recruiting round 1.", "info")
    return redirect(url_for("recruiting"))


@app.route('/debug_end_season')
def debug_end_season():
    # For testing, if no meets have been scheduled, create some debug meets.
    if not game_state.get("scheduled_meets"):
        # Create a few regular-season meets plus the mandatory postseason meets.
        # Regular meets:
        debug_meets = [
            Meet("Meet A", "2024-09-06", 6),  # Week 2
            Meet("Meet B", "2024-09-27", 5),  # Week 5
            Meet("Meet C", "2024-10-18", 7),  # Week 8
            Meet("Meet D", "2024-11-08", 6)   # Week 11
        ]
        # Manually set their weeks based on date calculations if needed.
        # Postseason meets (with no date, we set week manually):
        conf = Meet("Conference Championship", None, 10)
        conf.week = 13
        reg = Meet("Regional Championship", None, 10)
        reg.week = 15
        nat = Meet("National Championship", None, 10)
        nat.week = 16
        debug_meets.extend([conf, reg, nat])
        game_state["scheduled_meets"] = debug_meets

    # Prepopulate training plans and race results for weeks 1 to 16.
    for week in range(1, 17):
        # If no training plan exists for this week, set a default plan.
        if week not in game_state["training_plan"]:
            # Use a default plan. For simplicity, every day is "Easy Day" except Friday.
            default_plan = {
                "Monday": "Easy Day",
                "Tuesday": "Workout",
                "Wednesday": "Easy Day",
                "Thursday": "Workout",
                "Friday": "Easy Day",  # We will override below if needed.
                "Saturday": "Long Run",
                "Sunday": "Rest"
            }
            game_state["training_plan"][week] = default_plan

        # If a meet is scheduled in this week, simulate a race result.
        scheduled_meet = next((m for m in game_state["scheduled_meets"] if m.week == week), None)
        if scheduled_meet:
            # For simplicity, randomly determine a placement between 1 and 10 and assume 10 teams.
            placement = random.randint(1, 10)
            total = 10
            game_state["race_results"][week] = {
                "final": True,
                "skipped": False,
                "player_position": placement,
                "total_teams": total
            }
            # If the meet is scheduled in the current week, force Friday to "Race" in the training plan.
            game_state["training_plan"][week]["Friday"] = "Race"
        else:
            # If no meet is scheduled in the week and the previous week's training had "Race",
            # override Friday with "Easy Day".
            if week - 1 in game_state["training_plan"]:
                if game_state["training_plan"][week - 1].get("Friday") == "Race":
                    game_state["training_plan"][week]["Friday"] = "Easy Day"

    # For national qualification, you might want to update team ratings one last time.
    update_team_ratings()
    # Finally, set the current week to 17 (season complete).
    game_state["current_week"] = 16
    flash("DEBUG: Season fast-forwarded. Season has been played through.", "info")
    return redirect(url_for("dashboard"))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
    app.run(debug=True)
