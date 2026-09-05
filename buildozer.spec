[app]
title = pyTrainer
package.name = pyTrainer
package.domain = org.ptt
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,scheda,java
source.exclude_dirs = .git,.venv,venv,__pycache__,tests,.scratch,.buildozer,.docs,.opencode,.agents,.pytest_cache,bin,drive-cache,frames
source.exclude_patterns = token.json,credentials.json,service_account.json,*.scheda,*.work,*.work/*
version.regex = __version__\s*=\s*["']([^"']+)["']
version.filename = %(source.dir)s/kivy_app/version.py
requirements = python3,Kivy==2.3.1,KivyMD==2.0.0,materialyoucolor==3.0.3,materialshapes==0.3,pycairo==1.28.0,asyncgui==0.6.3,asynckivy==0.6.4,exceptiongroup,Pillow==11.3.0,plyer,google-auth==2.23.4,google-auth-oauthlib,google-api-python-client,google-auth-httplib2,google-api-core,googleapis-common-protos,proto-plus,protobuf,httplib2,pyparsing,uritemplate,cachetools,pyasn1,pyasn1-modules,rsa,yt-dlp,requests,urllib3,certifi,charset-normalizer,idna,pyjnius,android
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
