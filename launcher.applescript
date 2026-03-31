-- Shabbos Situation Monitor Launcher
-- Starts the server if not running, focuses existing Safari tab if it is.
-- Double-click to use; polls /health instead of blind delay.

set serverPort to "8080"
set dashboardURL to "http://127.0.0.1:" & serverPort
set maxWait to 30 -- seconds to wait for server startup

-- Check if server is already running
set serverPID to do shell script "lsof -i :" & serverPort & " -t 2>/dev/null || echo ''"
set serverRunning to (serverPID is not "")

if not serverRunning then
	-- Start the server in Terminal
	tell application "Terminal"
		activate
		do script "cd '/Users/Yitzi/code/shabbos-situation-monitor' && ./start.sh"
	end tell

	-- Poll /health until the server is ready (up to maxWait seconds)
	set isReady to false
	set waited to 0
	repeat while waited < maxWait
		delay 2
		set waited to waited + 2
		try
			set healthCheck to do shell script "curl -s -o /dev/null -w '%{http_code}' --max-time 2 " & dashboardURL & "/health 2>/dev/null || echo '000'"
			if healthCheck is "200" then
				set isReady to true
				exit repeat
			end if
		end try
	end repeat

	if not isReady then
		display dialog "Server failed to start after " & maxWait & " seconds." & return & return & "Check the Terminal window for errors." buttons {"OK"} default button "OK" with icon stop
		return
	end if
end if

-- Open or focus Safari at the dashboard URL
tell application "Safari"
	activate
	-- Look for an existing tab showing the dashboard
	set foundTab to false
	repeat with w in windows
		set tabIndex to 0
		repeat with t in tabs of w
			set tabIndex to tabIndex + 1
			if URL of t starts with dashboardURL then
				set current tab of w to tab tabIndex of w
				set index of w to 1
				set foundTab to true
				exit repeat
			end if
		end repeat
		if foundTab then exit repeat
	end repeat
	-- If no existing tab found, open a new one
	if not foundTab then
		if (count of windows) is 0 then
			make new document with properties {URL:dashboardURL}
		else
			tell window 1
				set current tab to (make new tab with properties {URL:dashboardURL})
			end tell
		end if
	end if
end tell
