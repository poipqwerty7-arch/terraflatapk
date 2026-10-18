[app]
title = Teraflat
package.name = teraflat
package.domain = org.teraflat

source.dir = .
source.include_exts = py,png,jpg,mp3,ogg,wav,xml,json
source.include_patterns = Textures/*,Music/*,Music/menu/*,Music/game/*
version = 0.1

# pygame на Android - самая капризная часть. Если сборка падает на pygame,
# смотри "Если не собралось" в инструкции.
requirements = python3,pygame,sdl2,sdl2_image,sdl2_mixer,sdl2_ttf

orientation = landscape
fullscreen = 1

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24

# Фиксируем старую стабильную версию python-for-android (Python 3.11):
# на свежем Python 3.14 pygame 2.1.0 из рецепта не компилируется
# (fatal error: 'longintrepr.h' file not found).
p4a.branch = v2024.01.21
android.archs = arm64-v8a
android.accept_sdk_license = True

# Для хранения миров хватает приватной папки приложения, доп. разрешения не нужны
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
