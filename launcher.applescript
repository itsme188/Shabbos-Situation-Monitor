tell application "Terminal"
	activate
	do script "cd '/Users/Yitzi/Desktop/shabbos situation monitor' && ./start.sh"
end tell

-- Wait for the server to come up, then open Safari
delay 5
tell application "Safari"
	activate
	open location "http://localhost:8080"
end tell
