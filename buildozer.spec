
[app]

title = Terraflat
package.name = terraflat
package.domain = org.teraflat
version = 0.2

source.dir = .
source.include_exts = py,png,jpg,jpeg,mp3,ogg,wav,xml,json,ttf
source.include_patterns = Textures/*,Music/*,Music/menu/*,Music/game/*

# Графика и звук
requirements = python3,pygame

# Иконка приложения
icon.filename = %(source.dir)s/icon.png

# Настройки экрана
orientation = landscape
fullscreen = 1

# Android
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

# Версия python-for-android
p4a.branch = v2023.05.21

# Release APK
android.release_artifact = apk
android.debug_artifact = apk

# Разрешения пока не запрашиваем
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
