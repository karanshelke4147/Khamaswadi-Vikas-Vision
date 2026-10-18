KHAMASWADI VIKAS - V3 UPGRADE

This V3 keeps the existing SQLite structure compatible and adds safe admin record management.

NEW FEATURES
1. Admin button in the top navigation
2. Active vs Archived issue separation
3. Archive / Restore issue (safe; data remains in database)
4. Permanent Delete (Admin only + confirmation)
5. Database SQL Backup button
6. Excel / CSV export includes Archived status
7. Admin dashboard shows archived count
8. Mobile-friendly admin action buttons
9. Existing search, ward/status/priority/category filters remain
10. Existing photo upload, public updates, PWA and dashboard remain

IMPORTANT
- Keep your existing khamaswadi.db. Do NOT delete it.
- This version automatically adds the archived columns if your old database does not have them.
- If your current project already has a khamaswadi.db, copy the V3 source files into that project folder; do not replace the database.
- The Admin credentials in this local version remain:
  Username: admin
  Password: khamaswadi123
- Before putting the app online, change authentication and SECRET_KEY.

RUN
1. Open the V3 project folder in VS Code.
2. Activate your existing virtual environment:
   .\.venv\Scripts\Activate.ps1
3. Install requirements if needed:
   pip install -r requirements.txt
4. Start:
   python app.py
5. Open:
   http://127.0.0.1:5000

ADMIN
Use the Admin button at the top of the website.

ARCHIVE
Archive hides an issue from the normal active dashboard but keeps its data. It can be restored from the Archived view.

DELETE
Permanent Delete removes the issue and its public update history. A confirmation box appears first. Use Backup before permanent deletion when the record matters.

BACKUP
The Admin dashboard has a Backup button. It downloads a timestamped SQL backup of the SQLite database.
