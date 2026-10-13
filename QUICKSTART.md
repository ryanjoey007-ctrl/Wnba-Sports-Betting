# Your Courtwise app

Courtwise is built. It is a personal WNBA forecasting app, not a betting service.
It is not yet hosted on a public website. You can run it on your own computer.
You do not need Git, an API key, or a paid service to try the demo.

## Start on Windows — every step

1. Open https://github.com/ryanjoey007-ctrl/Wnba-Sports-Betting in your browser. Sign in to GitHub if asked. If you see 404, make sure you are signed in to the account that owns this repository.
2. Near the top of the file list, select the green **Code** button, then **Download ZIP**. This downloads `Wnba-Sports-Betting-main.zip`.
3. In File Explorer, open **Downloads**. Right-click the ZIP and choose **Extract All → Extract**.
4. Open the extracted folder, then the inner **Wnba-Sports-Betting-main** folder. You are in the correct folder when you see `app.py` and `requirements.lock`.
5. Download the official [Python 3.12.10 Windows 64-bit installer](https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe). This is the standard installer for most Windows PCs. Run it. Tick **Add python.exe to PATH**, leave the Python launcher enabled, then click **Install Now**. When it finishes, click **Close**. If Python 3.12 is already installed, skip this step.
6. Return to the extracted folder. Click File Explorer's address bar at the top, type `cmd`, and press **Enter**. A black Command Prompt window opens in that folder. Keep it open.
7. Copy the following commands into that window, **one line at a time**, pressing Enter after each. Wait for each command to finish before running the next:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe app.py
```

The second command downloads dependencies and can take several minutes. The last command keeps running and displays **Running on**. It will not return to a command prompt while the app is running; this is expected.

8. Leave the black window open. Open **Edge** or **Chrome**. In the browser's address bar at the top (not a search box), type `127.0.0.1:5050` and press **Enter**. Courtwise should appear with the five starting players and a synthetic-demo banner.
9. To stop the app, click the black window and press **Ctrl+C**. To use it again, repeat step 6, then run only `.venv\Scripts\python.exe app.py`. Your imported data and saved forecasts are retained in the extracted folder's `data` directory; keep that folder.

If the browser says it cannot connect, make sure the last command is still running and shows **Running on**. If a command fails, copy the error text into this chat (never send API keys or passwords). If the ZIP appears in **Downloads** but files are still shown inside a compressed archive, extract it first; do not run from inside the ZIP. You do not need to publish a cloud environment to use the downloaded app on Windows.

## Mac or Linux

Download and extract the GitHub ZIP. In a terminal inside the folder containing `app.py`, with Python 3.12 installed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python app.py
```

Open the local address printed by the server and keep the terminal open. Stop with **Ctrl+C**.

## Try the app

- The green banner says **Synthetic demo workspace**. Every demo game, statistic, status and report is fictional. These examples must not be used to forecast actual games.
- Click a player’s name to see charts, game logs, availability examples, validation and the question box.
- Enter a points threshold such as **22.5**, then click **Apply**. Below, above and exactly-on probabilities appear under the table.
- Click **Save forecast snapshot** to keep that prediction. Later saves do not erase earlier ones.
- Click **Track a player** to add someone. Click the **×** at the end of a row to remove them. Removing preserves their stored records.

## When you want real data

Click **Use my data**. This workspace starts empty; it never silently uses the demo records.
Click **Data & sources** for CSV templates and the player IDs used by imports. Import historical logs and an upcoming schedule; at least five recorded appearances are needed for a forecast. Import a publicly sourced news report if you have one. Unknown availability stays unknown.

The **Refresh sources** button attempts a public ESPN schedule update. Live access was blocked in the build environment, so this adapter is not verified against live ESPN responses. It can fail on your machine too. CSV import is tested and works without external access. See `README.md` for exact CSV fields and source limitations.

The question box works without AI credentials using stored facts. Optional AI selects relevant evidence after a server-side key is configured. No key is required to use the numerical model.

The app updates only when you click refresh or run a scheduler. Closing the app stops its built-in scheduler. It does not keep checking games while your computer is off.
