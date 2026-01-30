#!/usr/bin/env python3
"""Quick test script to verify the server works."""

import sys
sys.path.insert(0, '.')

from server import app, update_all_feeds, cache
from datetime import datetime

print("Testing Shabbos Monitor Server")
print("=" * 50)

# Run fetchers
print("\n1. Fetching data...")
update_all_feeds()

# Check cache
print("\n2. Cache status:")
for name, data in cache.items():
    count = len(data['items'])
    error = data['error']
    status = 'OK' if count > 0 else 'FAIL'
    print(f"   {name}: {status} ({count} items)")
    if error:
        print(f"      Warning: {error}")

# Test template rendering
print("\n3. Testing template...")
with app.app_context():
    try:
        from flask import render_template
        html = render_template('index.html', cache=cache, generated_at=datetime.now(), refresh_interval=600)
        print(f"   Template OK ({len(html)} chars)")
    except Exception as e:
        print(f"   Template ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("\n4. Starting server on port 8080...")
print("   Open http://localhost:8080 in your browser")
print("   Press Ctrl+C to stop\n")
print("=" * 50)

app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
