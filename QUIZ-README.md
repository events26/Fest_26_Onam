# Onotsavam Quiz Buzzer

Teams buzz from their own phones. The projector shows the question, its four
options and whoever got there first. The quizmaster runs it from their own
phone, so the answer key never lands on the big screen.

Runs on the Python standard library — there is nothing to install.

Nothing on the main site links to any of this. The three pages are reachable
only by typing the URL.

## Running it

```
python quiz-server.py
```

It prints the three URLs. Open them:

| Who | Where |
|---|---|
| Teams | `http://<your-ip>:8000/` |
| Projector | `http://localhost:8000/display` |
| Quizmaster | `http://<your-ip>:8000/admin` — PIN `onam26` |

## Finding your IP so other people can open the page

The server prints the right address when it starts — that is the easy answer,
and it is usually all you need. To find it yourself:

**Windows.** Open Command Prompt and run:

```
ipconfig
```

Look for the adapter you are actually connected through — `Wireless LAN adapter
Wi-Fi` if you joined a hotspot. Take the **IPv4 Address**, something like
`192.168.1.6` or `172.20.10.3`. Ignore anything under a disconnected adapter,
anything starting `169.254` (means no network), and any `Virtual`/`VMware`/
`Hyper-V`/`WSL` adapters, which are not reachable from a phone.

**Mac.** System Settings → Wi-Fi → Details, or:

```
ipconfig getifaddr en0
```

**Check it before the quiz starts.** Open `http://<your-ip>:8000/` on one phone.
If that phone loads the page, every phone will.

**If a phone cannot reach it**, in order of likelihood:

1. **Windows Firewall blocked Python.** It asks once, on first run. If you
   clicked Cancel, phones time out with no other clue. Fix it in Windows
   Security → Firewall & network protection → Allow an app through firewall →
   find Python → tick **Private**.
2. **Not on the same network.** The laptop and every phone must be on the same
   hotspot, not one on office Wi-Fi and one on mobile data.
3. **Office or hotel Wi-Fi.** These almost always isolate clients from each
   other, so phones cannot reach the laptop at all no matter what you do. Use a
   phone hotspot instead — that is the fix, not a workaround.
4. The IP changed. Rejoining a network can hand out a new one. Restart the
   server and read the address it prints.

## Setting it up on the day

1. **Make a hotspot from a phone** and connect the laptop to it.
2. Start the server and say yes to the firewall prompt.
3. Put `/display` on the projector, press **Full screen**, then **Turn on
   sound** once. Browsers block audio until someone clicks, so this has to
   happen before the first question.
4. Open `/admin` on your own phone and enter the PIN.
5. Under **Teams & codes**, set the team names, then either type a code for
   each or tap **Generate codes**. Save.
6. Read each code out to **one person per team**. That phone holds the buzzer.
7. Teams open the join URL, pick their team, enter the code.

The projector's idle screen shows the join URL in large type, and the
scoreboard marks any team that has not signed in yet, so you can see at a
glance who is still missing.

## Team codes

Each team gets its own code, and only one phone can hold a team's buzzer at a
time. If a second phone signs in with the same code it **takes over**, and the
first one is told it has been signed out — so a dead battery cannot lock a team
out for the rest of the quiz. That does mean anyone with the code can take the
buzzer, which is why the codes go to one person per team rather than into the
group chat.

**Sign out** next to a team in the admin panel force-releases their buzzer.

A team left with a blank code can be joined by anyone, which is handy while
testing and worth clearing before you start.

## Questions from a Google Sheet

Make a sheet with these columns, in a tab called `Quiz`:

| Question | Option A | Option B | Option C | Option D | Answer |
|---|---|---|---|---|---|
| Onam falls in which Malayalam month? | Karkidakam | Medam | Thulam | Chingam | D |

- The **Answer** cell takes a letter (`A`–`D`) or the full option text.
- Header spelling is flexible (`Option A`, `OptionA` and `A` all work) and the
  columns can be in any order.
- Leave the option columns blank for an open question — the projector then
  shows just the question.
- Blank rows are skipped, so you can space the sheet out however you like.

Share the sheet as **anyone with the link can view**, or the server cannot read
it. Then copy the id out of the sheet URL — the part between `/d/` and `/edit` —
and paste it into **Question sheet** in the admin panel, or set `SHEET_ID` at
the top of `quiz-server.py`.

**Reload questions** pulls your latest edits without restarting, so you can keep
editing the sheet right up to the start.

If the sheet is unreachable when the server starts, it falls back to
`quiz-questions.json`, which ships with 18 Onam questions. If the connection
drops *during* the quiz, nothing happens — the questions are already in memory.

## Running a round

Read the question aloud from your phone, then:

- **Arm buzzers** — phones go live and start pulsing.
- Someone buzzes. Everyone else locks out instantly; the projector blooms in
  the winning team's colour and shows their reaction time.
- **Correct** (+10 and closes the question) or **Wrong — pass it on** (locks
  that team out and reopens the buzzers for everyone else).
- **Show the answer on screen** highlights the right option on the projector.
- **Next question ›**.

**Reset this question** reopens everything including lockouts, for when a
question has to be thrown out.

## Settings

Team names and codes are set from the admin panel. Everything else is at the top
of `quiz-server.py`:

- `ADMIN_PIN` — change it, especially if you are pushing this to GitHub.
- `POINTS_CORRECT` — 10 by default.
- `POINTS_WRONG` — 0. Set it negative (say `-5`) if speculative buzzing becomes
  a problem; it usually stops within one round of the first penalty.
- `PORT` — 8000.

Team names, codes and scores are written to `quiz-state.json` so a crash or a
restart mid-event does not cost you anything. That file is gitignored, because
it holds the codes — every host generates their own.

## About "who was actually first"

Once buzzing crosses a network, the server is ranking *when each buzz arrived*,
not when each thumb moved. A team on a weak signal can press earlier and still
lose by a few milliseconds.

Two things soften this. Every buzz landing within 150ms of the first is judged
together and sorted by arrival, which absorbs scheduling jitter rather than
letting whichever thread woke first win. And the phones hold an open connection
and warm the socket the moment a question is armed, so a buzz is not paying for
a fresh TCP handshake.

It is still a network, though. Announce before the quiz starts that the screen
is the final word, and the arguments stop.
