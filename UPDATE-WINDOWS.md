# Update your existing Windows app

These steps use Ryan's existing folder: `C:\Users\Ryan\Desktop\Wnba-Sports-Betting-main`.
Use your own app folder if it has moved. Keep the existing `data` folder and `.venv` folder.

1. In the PowerShell window running Courtwise, press **Ctrl+C** to stop it. Leave PowerShell open.
2. Make a backup: on your Desktop, right-click **Wnba-Sports-Betting-main**, select **Copy**, then paste it on your Desktop. Windows should create a second folder with “Copy” in its name. Leave that backup alone. It includes your saved data.
3. Open https://github.com/ryanjoey007-ctrl/Wnba-Sports-Betting . Click **Code → Download ZIP**. Sign in to the owning GitHub account if the repository isn't visible.
4. In **Downloads**, right-click the new ZIP and select **Extract All → Extract**. Open the new extracted folders until you see `app.py` (which Windows may show as `app`) alongside `requirements.lock`. This is the folder containing the new app files.
5. In that new folder, press **Ctrl+A**, then **Ctrl+C** to copy its contents. Open your ORIGINAL Desktop folder, `C:\Users\Ryan\Desktop\Wnba-Sports-Betting-main`, and press **Ctrl+V**. Choose **Replace the files in the destination** when Windows asks. Copy the contents into the existing folder; do not delete or replace the entire existing folder. The GitHub ZIP contains neither `data` nor `.venv`, so those existing folders should remain. Never delete the database to fix an update.
6. In PowerShell, run these lines one at a time, pressing Enter and waiting after each:

```powershell
cd "C:\Users\Ryan\Desktop\Wnba-Sports-Betting-main"
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe app.py
```

Scrolling dependency-install messages are normal. The final command stays running and shows **Running on**. If an error appears, stop and copy its text into the chat. Do not send keys or passwords.

7. In Edge or Chrome, open your local app as before by typing `127.0.0.1:5050` in the address bar. Press **Ctrl+F5** to reload its latest scripts and styles. Keep PowerShell open.

## Use the new features

1. Click **Data & sources → Load last 3 seasons of real logs**. Watch the progress beside the button; it shows the phase and number of downloads. If ESPN cannot respond, an error replaces the loading state within the time limit. Cancel import is available before completion.
2. On completion, click **View imported data** beside the progress message. It switches to the real-data workspace. Alternatively, close the dialog and choose **Use my data** on the dashboard. Importing does not silently replace demo records. If your older installation already completed with HTTP 200, those records remain saved; switch to real-data mode to see them without importing again.
3. Click **Refresh sources** for upcoming games and public news, or **Data & sources → Refresh ESPN news & reports** for news alone.
4. Click a player's name. The new **Scoring by day of the month** chart shows average points for calendar days 1–31, with sample counts and a season filter. Use the day selector to inspect a bucket and its source-linked game records.
5. Enter a threshold such as **22.5** on the dashboard, click **Apply**, then open a player. The calendar panel shows historical below/above/tie frequencies, clearly separate from model probabilities.

Public news and injury reports include source links, publication dates and retrieval dates. An “undisclosed” injury appears only when publicly reported. Old or missing reports do not establish current availability. It is legitimate for a player to have historical logs but no upcoming game in the loaded schedule. Calendar averages are descriptive; they do not change forecasts or demonstrate betting profit.

## If Use my data looks blank

The updated dashboard shows GAME LOGS and RECENT AVG separately from next-game forecasts. The banner reports how many real logs are loaded. Click a player to see Recent game log and the calendar chart. If those logs exist but future projections are dashes, there is no upcoming game in the loaded schedule or the player is ruled out; historical imports are not missing. Load schedules with Refresh sources when available, without inventing fixtures. If Recent game log says No game logs imported, copy the result message from the history import into chat; an HTTP 200 alone can include an empty result, and the imported count must be checked. If rows tell you to restart for counts, stop and restart the Python app and press Ctrl+F5: the browser was serving newer scripts against an older running server. Do not delete the data folder.
