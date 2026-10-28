<!-- Plain-language walkthrough of the project and demo.ipynb for readers who do not code. Every number quoted here is copied from the committed outputs of demo.ipynb (offline mode). -->

# A plain-language guide to the Boston 311 Crew Planner

This guide is for anyone who wants to understand and follow this project without knowing how to code: teammates working on the report or video, graders, or anyone curious. You do not need to read or change any code. You only need to know where to look and what the numbers mean.

**Contents**

1. [The project in one page](#1-the-project-in-one-page)
2. [Words you will see](#2-words-you-will-see)
3. [Two ways to follow along](#3-two-ways-to-follow-along)
4. [How a notebook works](#4-how-a-notebook-works)
5. [Walkthrough, section by section](#5-walkthrough-section-by-section)
6. [If something goes wrong](#6-if-something-goes-wrong)
7. [Where everything else lives](#7-where-everything-else-lives)

---

## 1. The project in one page

**The city's problem.** Boston residents report problems such as potholes, broken street lights, and illegally parked cars through the 311 service. Each request goes to a city department, and each department has a limited number of work crews. If a department has too few crews, requests pile up and miss their deadlines. If it has too many, the city pays for idle crews.

**Our assignment.** The course gave us a simplified "challenge model" of four departments:

| Department | Short code | Crews in January 2025 |
|---|---|---|
| Public Works | PWDx | 50 |
| Transportation | BTDT | 18 |
| Parks & Recreation | PARK | 10 |
| Inspectional Services | ISD | 16 |

The model also fixes the rules: how many requests a crew closes per day, what a crew costs, that a new hire needs one month of training, that releasing a crew costs 25% of a year's pay, that Parks may add cheaper short-term seasonal crews from April to October, and that every late request costs a penalty ($20 when it misses its deadline, plus $100 more if it is still open 30 days later). These are the course's assumed numbers, not Boston's real budget.

**What we built.** The project has two halves.

* **A staffing planner.** It looks at real 2023 and 2024 requests, predicts how many requests will arrive each month of 2025, and decides month by month when to hire, release, or add seasonal crews. It then tests that plan in a simulation and compares it with simply keeping January's crews all year.
* **An intake assistant.** This is the "GenAI" half. A resident types a problem in their own words ("there's a dead raccoon on Adams St"), and the assistant works out which official request type it is and which department should handle it. It uses a large language model (an AI model from OpenAI), but ordinary code makes the final routing decision.

**The headline results** (from the notebook):

| | Our plan | Keep January's crews all year |
|---|---|---|
| Total 2025 cost (crews, severance, and penalties) | **$16.39M** | $19.47M |
| Requests closed on time | **90%** | 22% |
| Requests still open on December 31 | 1,441 | 27,579 |

The intake assistant made the right decision on all 40 messages in its test set and picked the right request type for 33 of 34.

**Where the results live.** Everything is shown in one file, the notebook [`demo.ipynb`](../demo.ipynb). The rest of this guide walks through it.

---

## 2. Words you will see

You can skip this section and come back to it when a word is unfamiliar.

**Staffing words**

* **Crew.** One work team. Each department's crews close a fixed number of requests per working day (Public Works 12, Transportation 15, Parks 6, Inspectional Services 4).
* **Capacity.** How many requests a department can close in a month: crews x requests per crew per day x 21 working days.
* **Target date (deadline).** The date the city aims to close a request by. Some request types have no target date.
* **On time / on-time rate.** A request is on time if it is closed by its target date. An on-time rate of 0.90 means 90%.
* **Overdue event / long-overdue event.** The two penalties: $20 when a request passes its target date while still open, and $100 more if it is still open 30 days after that.
* **Backlog / open requests.** Requests that have arrived but are not closed yet.
* **Hire.** Ordering a new permanent crew. It costs one month of training pay and starts working the month after it is ordered.
* **Release.** Giving one month's notice to remove a permanent crew. It costs 25% of the crew's annual cost.
* **Seasonal crew.** Parks only, April to October. Costs 1.3 times a regular crew per month but needs no training and no release cost.

**Planning and testing words**

* **Forecast.** Our prediction of how many requests each department will get in each month of 2025.
* **Workload.** A full, made-up list of every 2025 request: the day it arrives, its type, and its deadline. It is built from the forecast and from patterns in the real 2023 and 2024 data. The simulator needs individual requests, not just monthly totals.
* **Planning workload vs. evaluation workload.** Two separate made-up workloads built the same way but with different random draws. The planner only ever sees the planning workload. The plan is then graded on the evaluation workload. This is like studying from one practice exam and being graded on a different one, so the plan cannot "memorize the answers."
* **Simulator.** A program that plays out 2025 day by day: requests arrive, crews close the oldest ones first, and late requests collect penalties.
* **Baseline.** The comparison plan: keep January's crews all year and do nothing else.
* **Heuristic plan / frozen plan.** Our plan. "Heuristic" means it follows sensible rules of thumb rather than trying every possible plan. "Frozen" means once its 12 months of decisions are made, they are locked before testing.
* **Scenario.** A "what if" version of the evaluation workload: demand 20% higher (`plus20`), 20% lower (`minus20`), or a snowstorm (`spike`).

**Intake assistant words**

* **LLM (large language model).** An AI model that reads and writes text. Here it is OpenAI's `gpt-6.1-sol`.
* **Request type.** One of 163 official 311 categories, such as "Pick up Dead Animal" or "Street Light Outages."
* **Retrieval / RAG.** Before asking the AI, the code searches the official list and pulls out the 8 closest types, the way a library search narrows a shelf. The AI then chooses only from those 8. RAG stands for "retrieval-augmented generation."
* **Alias.** An everyday phrase for an official type ("lamp post" for street light). Aliases make the search work with residents' wording.
* **Structured output.** The AI must answer by filling in a fixed form (which type, how confident, whether it is unclear) instead of writing free text. This makes its answer checkable by code.
* **LangChain and LangGraph.** Software toolkits the course asked us to use. LangChain talks to the AI model. LangGraph runs the assistant's steps in order, including pausing to ask the resident a question.
* **Decisions.** `ROUTE` (send it to a department), `CLARIFY` (ask one question first), `TRIAGE` (hand it to a person), `REJECTED` (nothing was typed).
* **Queue.** The specific team inside a department that handles a request.

**Run words**

* **Offline mode.** The default. The notebook replays AI answers that were recorded during a real live run, so it needs no internet and no API key, and gives the same results every time.
* **Live mode.** The notebook calls OpenAI for real. It needs an API key (a private password for the OpenAI service) and is only used for messages that have no recording yet.
* **Manifest.** A receipt for a run, listing exactly which data, settings, and software versions were used.

---

## 3. Two ways to follow along

### Option A: just read it (recommended, nothing to install)

The notebook in the repository has already been run, so every table and chart is saved inside it.

1. Open the repository on GitHub in a web browser.
2. Click **`demo.ipynb`**. GitHub shows it as a page with text, tables, and charts.
3. Read it from top to bottom alongside [section 5](#5-walkthrough-section-by-section) of this guide.

If GitHub says it cannot render the file, wait a moment and refresh. It is a large page.

### Option B: run it yourself

Running it yourself proves the results are reproducible. Offline mode needs no API key. Expect about 15 to 30 minutes the first time, mostly installing software. You will type a few commands into a **terminal** (a text window for giving your computer commands: "Terminal" on macOS, "PowerShell" on Windows). Copy and paste each command exactly, then press Enter.

**Step 1. Install the tools (once).**

* **Python 3.12** from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add python.exe to PATH"** on the first installer screen. Or install it with one command: `winget install Python.Python.3.12` in PowerShell on Windows, or `brew install python@3.12` on a Mac with Homebrew.
* **Visual Studio Code** (VS Code) from [code.visualstudio.com](https://code.visualstudio.com/). Open it, click the Extensions icon (four squares) on the left, and install the **Python** and **Jupyter** extensions published by Microsoft. Anaconda's Jupyter also works if you already have it.

**Step 2. Get the project.** On the repository's GitHub page, click the green **Code** button, then **Download ZIP**. Unzip it somewhere easy to find, such as your Desktop.

**Step 3. Open a terminal in the project folder.** In VS Code choose **File > Open Folder**, pick the unzipped folder (the one that contains `demo.ipynb` and `README.md`), then choose **Terminal > New Terminal**. A terminal opens at the bottom, already inside the project folder.

**Step 4. Set up the project's own Python environment.** Paste these one at a time. The first creates a private Python environment named `.venv` so nothing else on your computer is affected.

```bash
python -m venv .venv
```

Then switch it on:

* Windows: `.venv\Scripts\activate`
* macOS or Linux: `source .venv/bin/activate`

You should now see `(.venv)` at the start of the terminal line. Then install everything the project needs (this takes a few minutes and prints a lot of text, which is normal):

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
python -m ipykernel install --user --name boston311 --display-name "Python (boston311)"
```

The last command registers this environment with Jupyter under the name **Python (boston311)**.

On Windows, if `python` is "not recognized," close and reopen VS Code, or use `py -3.12` in place of `python` for the first command. Use `py -3.12` too if you have more than one Python installed, so the environment gets 3.12 and not a newer version.

**Step 5. Open and run the notebook.**

1. In VS Code's file list on the left, click **`demo.ipynb`**.
2. At the top right, click the kernel button (it may say **Select Kernel**) and choose **Python (boston311)**. If it is not listed, choose the Python environment called `.venv` instead.
3. Click **Run All** at the top.
4. Wait. Cells run one after another from top to bottom. A cell that is still running shows a spinning icon. The whole notebook takes a few minutes. The Parks section (section 4 of the notebook) is the slowest part, because it rebuilds the plan ten times.

When it finishes, your tables and charts should match the ones already saved on GitHub. Running the notebook overwrites the saved results with your own, which should be identical.

**Optional: no notebook viewer at all.** With `.venv` switched on, this one command runs everything and writes all the tables and charts into the `outputs/` folder:

```bash
python scripts/run_all.py
```

---

## 4. How a notebook works

A notebook is a document made of **cells** stacked top to bottom.

* **Text cells** explain what is happening, for human readers.
* **Code cells** are instructions for the computer. They have a grey box, and usually a number in brackets on the left, such as `[5]`, showing the order they ran in.
* **Outputs** appear directly under each code cell: a table, a chart, or a few lines of printed text. **The outputs are what matter for you.** You can skip the code itself.

Tips for reading the outputs:

* **Tables** have row labels on the left and column names across the top. Some tables have two header rows: the top row names a measure (for example `total_cost`), and the row below splits it into `baseline` and `heuristic` (our plan).
* Rates are written as decimals: **0.90 means 90%**.
* Department codes are used everywhere: PWDx, BTDT, PARK, ISD. `ALL` means the four departments added together.
* Months are numbers: 1 is January, 12 is December.
* Wide tables may wrap onto several lines or need sideways scrolling.

If you are running it yourself: **Run All** runs every cell in order. If anything looks wrong, use **Restart** (or **Restart Kernel**) and then **Run All** again. Running cells out of order can confuse the notebook, because later cells depend on results from earlier ones.

---

## 5. Walkthrough, section by section

Each part below matches a heading in the notebook. For each one: the question it answers, what the computer does, how to read the output, and what to take away.

### Title cell and the setup cell

**What it is.** The first text cell lists the team and summarizes the six parts of the notebook.

**The first code cell** loads the project's tools and sets `MODE = "offline"`. Its only output is one line:

```
mode: offline | model: gpt-6.1-sol | prompt: classify-v2 | catalog: catalog-v2
```

This confirms the notebook is replaying recorded AI answers and names the exact AI model, prompt version, and catalog version used. If this cell instead shows an error saying `boston311` is not installed, see [section 6](#6-if-something-goes-wrong).

### Notebook section 1: Data and reconciliation

**Question.** Did we load the city's data correctly?

**What happens.** The real 2023 and 2024 data (about 180 MB per year) was downloaded once from the city's open data site, Analyze Boston, and boiled down into small summary tables that are saved in the project. This cell reads a summary of that process. It does not download anything.

**How to read the three tables.**

1. **Our counts vs. the project page.** For each department, `page` is the 2024 request count printed on the assignment page, `ours` is what our code counted, and `match` should say `True`. All four match exactly (for example Public Works: 157,610 and 157,610). This is our main evidence that the data was loaded and filtered correctly.
2. **Cleaning summary by year.** `rows_read` is every request in the file. `out_of_scope_departments_excluded` are requests for other departments, which we drop. `in_scope_rows` is what is left (276,417 for 2024). `duplicates_removed` is 0, meaning no request appeared twice. `target_classes` splits requests by whether they have a usable deadline: `valid` (has one) or `missing` (has none).
3. **Source files.** The size of each downloaded file, its `md5` (a digital fingerprint the city publishes, so we can prove the file was not corrupted or altered), and when the city last updated it.

**Take away.** The data matches the assignment exactly, and its origin can be checked.

### Notebook section 2: 2025 demand forecast

**Question.** How many requests will each department get in each month of 2025?

**What happens.** We use the simplest sensible method, called **seasonal naive**: each month of 2025 is predicted to be the same as that month of 2024. With only two years of history, there is no fair way to prove a fancier method would do better.

**How to read the outputs.**

* **Forecast table.** Rows are months 1 to 12, columns are departments. For example, Public Works is predicted to get 13,582 requests in January and 16,398 in August.
* **Backtest table.** A "backtest" checks how the same method would have done a year earlier, predicting 2024 from 2023. `mape_pct` is the average monthly miss in percent (Transportation was the most accurate at 7.6%, Parks the least at 17.7%). `annual_bias_pct` shows whether the yearly total came out too high (positive) or too low (negative). Public Works was 8.7% too high.
* **Bar charts.** One small chart per department, one bar per month. Parks has a clear summer peak. Public Works peaks in August and September.

**Take away.** The forecast is simple and its typical error is around 8 to 18%. The later "20% higher" and "20% lower" scenarios are wide enough to cover errors of this size.

### Notebook section 3: Workloads

**Question.** What individual requests will the simulator play out?

**What happens.** The forecast only gives monthly totals. The simulator needs each request with its own arrival day and deadline, so the code builds full made-up lists of 2025 requests. The number of requests of each type follows the forecast and 2024's mix exactly. Each deadline is drawn at random from real deadlines for that type in 2023 and 2024, using a fixed random "seed" so the same list comes out every time.

**How to read the table.** One row per workload:

| Workload | Requests | Meaning |
|---|---|---|
| `planning` | 276,417 | The only one the planner sees |
| `base` | 276,417 | The separate one used to grade the plan |
| `plus20` | 331,701 | `base` with 20% more requests added |
| `minus20` | 221,133 | `base` with 20% of requests removed |
| `spike` | 278,905 | `base` plus a snowstorm: Public Works requests tripled on February 10 to 12 |

The other two columns split each workload into requests with a deadline and without one.

**Take away.** The plan is made on one workload and graded on another. The "what if" scenarios only add or remove requests from the grading workload, so any difference between scenarios comes from demand alone.

### Notebook section 4: The frozen staffing plan

**Question.** When should each department hire, release, or add seasonal crews?

**What happens.** At the start of each month, the planner looks ahead using only the planning workload and follows three rules, in this order:

1. **Parks seasonal crews (April to October).** Add the fewest seasonal crews that keep at least 93% of that month's due requests on time. 93% was Parks' own on-time rate in 2024, so the goal is "no worse than last year."
2. **Hire** only if a shortage is predicted in **both** of the next two months, and hire only the smaller of the two shortages. This avoids paying for training and possible severance to cover a one-month blip. No hiring after October. Parks never hires a permanent crew that would start in its season, because seasonal crews are cheaper for that.
3. **Release** a crew only if no hire was ordered that month and a five-month look-ahead shows the release would not cause more late requests, would not cost more (severance included), and would not grow the backlog. No releases after August.

After December, all decisions are locked ("frozen").

**How to read the outputs.**

* **Plan table.** Four groups of columns, each split by department: `regular_crews` (permanent crews working that month), `hires_ordered`, `releases_noticed`, and `seasonal_crews`. For example, Transportation (BTDT) starts at 18 crews and ends the year at 26.
* **Decision log.** Plain-English lines explaining each decision, such as:

  > PWDx: month 1: projected shortage 2 crews in month 2 and 4 in month 3; ordered 2 hire(s), productive from month 2

  This reads: "In January, Public Works expects to be 2 crews short in February and 4 short in March, so it orders the smaller number, 2 hires, who start in February." Parks lines also show hires being **blocked** in spring because those crews would start during the season, and seasonal crews being used instead.
* **Bar charts.** Crews working each month per department. Blue is regular crews, orange is seasonal crews stacked on top, and the dashed line is January's crew count.

**In total,** the plan hires 20 Public Works crews, 8 Transportation, 9 Inspectional Services, and 1 Parks crew. It uses 42 seasonal crew-months in Parks, mostly from May to August. It releases no one, because each time a release is allowed the look-ahead still sees the September peak coming.

### "Why a 93% service floor for Parks seasonal crews?"

**Question.** Is 93% a reasonable target, or would another target be better?

**What happens.** The code re-makes the entire plan for a range of targets (50%, 70%, and so on, up to "remove every avoidable miss," which is 100%) and grades Parks each time. This is the slowest cell in the notebook.

**How to read the table and chart.** Each row is one target. `parks_total_cost` is Parks' total 2025 cost, `parks_on_time_rate` is its on-time rate, `seasonal_crew_months` is how many seasonal crews were used in total across the season, and `cost_per_extra_point` is roughly how much each extra percentage point of on-time service cost compared with the row above. The `chosen` column marks the 93% row as `True`.

The chart plots cost (up) against on-time rate (across). The line is fairly flat up to about 93 to 95% on time and then shoots upward. One row (85%) shows a negative cost per point: there, the planner's month-by-month choices happened to make the higher target slightly cheaper. It does not change the overall shape.

**Take away.** Going from 21% to 95% on time costs about $117K more than doing nothing. Beyond the 93% target, each extra point costs between $69K and about $480K. Aiming for 100% would cost $575K more for 2.4 extra points. Why set a service target at all? With only a $20 penalty per late request, a rule that only minimizes cost would accept most late requests. This is a public service, so the team put service first and let cost decide how to reach it.

### Notebook section 5: Scoring the frozen plan against January's crews

**Question.** Is our plan actually better than doing nothing?

**What happens.** Both plans are played out day by day by the same simulator on the same grading workload, which the planner never saw. The code also runs accounting checks on every result: every request is accounted for (open at the start + arrived = closed + open at the end), every hire and release lines up with an order one month earlier, no request is penalized twice for the same thing, and the cost parts add up to the total. The printed line "Reconciliation checks passed for all 8 plan x scenario combinations" means all of these checks passed.

**How to read the comparison table.** Rows are departments (and `ALL`). Each measure has a `baseline` column and a `heuristic` (our plan) column:

* `staff_cost`: crew pay, training months, and severance.
* `penalty_cost`: the $20 and $100 late penalties.
* `total_cost`: the two added together.
* `overdue_events`, `long_overdue_events`: how many penalties of each kind.
* `on_time_rate`: share of requests due in 2025 that closed on time.
* `open_dec31`: requests still open at year end.

**What the numbers say.**

| | Baseline | Our plan |
|---|---|---|
| Crew cost (all departments) | $11.92M | $15.92M |
| Penalty cost (all departments) | $7.55M | $0.48M |
| **Total cost** | **$19.47M** | **$16.39M** |
| On-time rate | 22% | 90% |

We spend about $4.0M more on crews and save about $7.1M in penalties. The biggest winner is Transportation, the department the assignment singles out: on time goes from 12% to 89% and its cost falls from $6.79M to $2.91M.

Not every department is cheaper. Inspectional Services costs more under our plan ($3.16M vs. $2.53M), and Public Works and Parks cost about the same or slightly more. In return, all three go from roughly 21% to 57% on time to roughly 89% to 95%.

Why is the baseline so bad (22% on time) when the real 2024 rates were much higher? Under the course's assumed numbers, January's crews cannot keep up with demand in any department, so a backlog builds all year. The comparison shows what happens inside the challenge model, not in Boston's real operations.

### Dynamic staffing table

**What it is.** The month-by-month table the assignment asks for: one row per department per month (48 rows), for our plan on the grading workload.

**How to read a row.** Take the first row, Public Works in January:

* `regular_crews` 50 and `hires_ordered` 2: 50 crews are working, and 2 new hires are ordered to start in February.
* `capacity` 12,600: 50 crews x 12 requests per day x 21 working days.
* `arrivals` 13,582 and `closed` 12,226: more requests came in than were closed. (Closed is a bit below capacity because some days run out of requests that have already arrived.)
* `overdue_events` 1,683: requests that passed their deadline that month.
* `open_end` 1,356: requests still open at the end of January.
* `total_cost` $596,993.33: 50 crews' pay, plus training pay for the 2 new hires, plus 1,683 x $20 in penalties.

The other columns are `releases_noticed` and `seasonal_crews` (Parks only). The long-overdue column is 0 throughout under our plan.

### Notebook section 6: Sensitivity analysis

**Question.** What if 2025 turns out differently from the forecast?

**What happens.** The same frozen plan, with no re-planning, and the baseline are replayed on the three "what if" workloads.

**What the numbers say.**

| Scenario | Our plan: cost | Our plan: on time | Baseline: cost | Baseline: on time |
|---|---|---|---|---|
| Base | $16.39M | 90% | $19.47M | 22% |
| Demand 20% higher | $20.85M | 12% | $33.20M | 8% |
| Demand 20% lower | $16.12M | 95% | $13.09M | 75% |
| Snowstorm | $16.76M | 82% | $20.36M | 16% |

The bar chart shows the same total costs side by side.

**Take away.**

* **Demand 20% higher:** our plan falls behind badly (12% on time), though it still costs far less than the baseline.
* **Demand 20% lower:** our plan is now overstaffed, and keeping January's crews would have been cheaper.
* **Snowstorm:** the plan absorbs it at modest extra cost.

A plan made once in January cannot respond when demand changes. A natural next step would be re-planning during the year as real requests come in.

### Year-end disclosures

**Question.** What is left unfinished on December 31?

**How to read it.** One row per department. `costs_accrued` is the 2025 total cost. The open requests at year end are split into: already late and charged (`open_overdue_charged`), late but whose $100 charge would fall in 2026 (`long_threshold_in_2026`), not yet due (`not_yet_due`), and with no deadline (`open_no_target`). For Public Works, 176 + 622 + 68 = 866 open requests. The hire and notice columns for 2026 are all 0. `due_in_2025` and `on_time_rate` show how many requests had a 2025 deadline and the share met.

**Take away.** Nothing is quietly dropped at year end. Costs count only within 2025, and leftover work is listed openly.

### Notebook section 7: The intake assistant

**Question.** Can an AI assistant send a resident's plain-language message to the right place?

**How it works**, step by step:

1. **Check the input.** An empty message is rejected straight away.
2. **Retrieve.** Search the 163 official request types (names, descriptions, and aliases) and keep the 8 closest.
3. **Classify.** The AI model picks one of those 8 by filling in a fixed form.
4. **Decide, in code, not by the AI.** The code checks the AI's choice. If it is valid and the request type has one clear department, it routes. If the message is too vague, it asks **one** clarifying question. Otherwise it hands the message to a person (triage).

**Two-tier routing.** In the city's real data, many request types are handled by different teams depending on the address. So the assistant names a **department** only if one of our four departments handled at least 90% of that type's requests in 2023 and 2024. It names an **exact queue** only if one queue handled at least 90%. Otherwise it says the queue is "assigned by location" or "assigned by the department."

**The five demo messages and what happened:**

| Message | Decision | Why |
|---|---|---|
| "A car is parked in front of my driveway and I can't get out." | ROUTE | Parking Enforcement, Transportation, with an exact queue |
| "dead raccoon in the middle of the road on Adams St" | ROUTE | Pick up Dead Animal, Public Works, queue assigned by location |
| "Huge pothole on Tremont St..." | TRIAGE | Correctly recognized as a pothole, but potholes are split between Public Works (84%) and the Water and Sewer Commission (14%), so a person decides |
| "Someone broke into my car last night..." | TRIAGE | A police matter, not one of our four departments. The reply points to 911 for emergencies |
| (empty message) | REJECTED | Nothing to route |

Every routed reply also gives the type's past on-time rate and typical time to close, labeled as past performance, not a promise. Every reply ends by stating that nothing was actually submitted to the city.

**The clarification example.** The resident writes "There's a light out." The assistant asks: "Is it a streetlight, a traffic signal, or a light in a park?" The resident answers that it is a street light in front of their house, and the assistant routes it to Street Light Outages in Public Works.

### Accuracy on the dev and test sets

**Question.** How often does the assistant get it right?

**What happens.** The assistant is run on two sets of practice messages. The **dev set** (18 messages) was used to tune the assistant. The **test set** (40 messages) was kept aside: it was not used to tune the prompts, the everyday phrases, or the score threshold, so it is the fairer measure. One later rule change (when the AI's pick and the search's top result agree, the score threshold is skipped) was prompted by a test message, so the test set is not completely untouched. The test set mixes clear requests, rewordings, easily confused types, vague messages, messages with several problems, out-of-scope messages, and an empty message. The team reviewed both sets and corrected six expected answers.

**How to read the metrics table.** Each metric shows `correct`, `total`, and `percent`, for dev and for test:

* **Decision accuracy:** did it reach the right final outcome (route, triage, or reject), counting the answer it got after asking a question when it asked one? Test: 40 of 40.
* **Type accuracy:** for messages that have a correct request type, did it pick that type? Test: 33 of 34.
* **Department accuracy:** for messages that should reach a department, did they reach the right one? Test: 29 of 29.
* **Queue accuracy:** whether the exact queue, or the "assigned by location / by department" label, was right.
* **Auto-route precision:** of the messages it routed on its own, how many had both the right type and the right department? Test: 28 of 29. This matters most, because a wrong automatic route sends a crew to the wrong job.
* **Auto-route coverage:** of the messages that should have been routed, how many it actually routed.
* **Clarification rate / triage rate:** how often it asked a question, or handed off to a person. On the test set it asked a question 20% of the time (8 of 40) and handed off 22.5% of the time (9 of 40).

**Retrieval table.** This shows how often the correct type was among the 8 search results: 100% with aliases, 47% without. The everyday phrases make a big difference.

**The one test mistake** (last table): "the restaurant on the corner has mice running..." was routed as Rodent Activity instead of a restaurant sanitation type. The department was right; the queue was not.

### Notebook section 8: Other consideration, neighborhood equity

**Question.** In 2023 and 2024, did some neighborhoods get worse on-time service than others for the same kinds of requests?

**What happens.** Neighborhoods report different mixes of problems, and some types are naturally slower. So for each neighborhood the code works out an **expected** on-time rate: what it would have been if each of its requests had been served at that type's citywide rate. The **gap** is actual minus expected, in percentage points.

**How to read the outputs.** The summary table lists, for each department, the range of raw on-time rates across neighborhoods and the neighborhoods with the largest negative and positive gaps. The bar chart shows Transportation by neighborhood. Bars to the left of the zero line did worse than expected, and bars to the right did better. Neighborhoods with too few requests are left out of the chart.

**Take away.** Public Works, Parks, and Inspectional Services stay within about 4 points of expected everywhere. Transportation varies most: West Roxbury is 13.3 points below expected, and South Boston / Waterfront 10.8 points above. This describes a pattern. It does not prove a cause, and it does not account for population.

### Notebook section 9: Run manifest

**What it is.** A "receipt" for the run, saved as a file in `outputs/manifests/`. The printed lines show when the run happened, the mode (offline), the last date of data used for training (December 31, 2024), the random seeds for the planning and grading workloads, the AI model settings, and that 19 input files were fingerprinted. Anyone can use this receipt to check that a later run used the same inputs.

### Notes and limits

The notebook ends with the main caveats, repeated here in plain terms:

* The costs, crew capacities, and penalties are the course's assumptions, and the 21-day working month is simplified.
* The plan is graded on made-up 2025 requests, not on real 2025 requests.
* The team reviewed the request-type mappings, everyday phrases, and test messages. Approval means they match past city routing, not that the city confirmed them. Phrases for 10 types are still unconfirmed, and the test messages are a small demonstration, not proof of how the assistant would do with real residents.
* The 93% Parks target is a policy choice backed by the cost-versus-service comparison, not the single "best" answer.
* Authorship, and how AI was used, are in the Authorship section of the [README](../README.md#authorship).

---

## 6. If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `No module named 'boston311'` in the first code cell | The notebook is using the wrong Python | Change the kernel to **Python (boston311)** (VS Code: kernel button at top right; Jupyter: **Kernel > Change Kernel**). If it is not listed, repeat step 4 of [Option B](#option-b-run-it-yourself) with `(.venv)` showing |
| `python` is "not recognized" or "command not found" | Python is not installed or not on the PATH | Reinstall Python and tick "Add python.exe to PATH" (Windows), or try `py` or `python3` |
| `(.venv)` is not shown in the terminal | The environment is not switched on | Run the activate command from step 4 again |
| Install errors mentioning SSL or certificates | Often antivirus or a work network scanning web traffic | Run `python -m pip install --upgrade pip` first, then retry. See the README note for Windows |
| A cell seems stuck | Some cells are slow, especially the Parks section | Wait a few minutes. If it truly hangs, **Restart** the kernel and **Run All** |
| An error about `OPENAI_API_KEY` | The notebook was switched to live mode | Set `MODE = "offline"` in the first code cell, or add a key to a `.env` file as the README describes |
| Results differ from the saved ones | Cells were run out of order, or a setting was changed | **Restart** and **Run All** with `MODE = "offline"` |

---

## 7. Where everything else lives

You do not need any of these to follow the notebook, but they are useful for the report and video.

| File | What it is |
|---|---|
| [`README.md`](../README.md) | Setup instructions, architecture diagram, authorship |
| [`docs/report.md`](report.md) | Draft written report with the same results in prose |
| [`docs/architecture.md`](architecture.md) | The full design specification |
| [`docs/decisions.md`](decisions.md) | Every design decision the team made, and why |
| [`docs/review_guide.md`](review_guide.md) | A technical guide for code reviewers |
| `outputs/` | Every result table as a spreadsheet-friendly CSV file, plus the charts in `outputs/figures/` |
| `data/eval/` | The dev and test messages used to grade the intake assistant |

The CSV files in `outputs/` open in Excel, Numbers, or Google Sheets, which may be easier for exploring the numbers than the notebook.
