-- Check if server is already running on port 8080
set serverRunning to (do shell script "lsof -i :8080 -t 2>/dev/null || echo ''")

if serverRunning is "" then
	-- No server running — start it
	tell application "Terminal"
		activate
		do script "cd '/Users/Yitzi/Desktop/shabbos situation monitor' && ./start.sh"
	end tell
	-- Wait for the server to come up
	delay 5
end if

-- Open Safari either way (to view the dashboard)
tell application "Safari"
	activate
	open location "http://localhost:8080"
end tell
