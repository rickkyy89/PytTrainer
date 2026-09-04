[app]
title = pyTrainer
package.name = pyTrainer
package.domain = org.ptt
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,scheda,java
source.exclude_dirs = .git,.venv,venv,__pycache__,tests,.scratch,.buildozer,.docs,.opencode,.agents,.pytest_cache,bin,drive-cache,frames
source.exclude_patterns = token.json,credentials.json,service_account.json,*.scheda,*.work,*.work/*
version = 0.1
requirements = python3,kivy,plyer,google-auth,google-auth-oauthlib,google-api-python-client,google-auth-httplib2,yt-dlp,pillow,requests,urllib3,certifi,charset-normalizer,idna,pyjnius
orientation = all
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.permissions = INTERNET,VIBRATE,POST_NOTIFICATIONS
android.gradle_dependencies = com.google.android.gms:play-services-auth:21.2.0
android.add_src = kivy_app/android/src

[buildozer]
log_level = 2
warn_on_root = 1
