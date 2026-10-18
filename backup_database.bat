@echo off
if not exist backups mkdir backups
copy /Y khamaswadi.db backups\khamaswadi_%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%.db
pause
