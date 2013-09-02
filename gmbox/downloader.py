#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import threading
import urllib
import traceback
from config import CONFIG

class Downloader(threading.Thread):

    def __init__(self, song, callback):
        threading.Thread.__init__(self)
        self.song = song
        self.callback = callback

    def run(self):
        self.song.remove_lock = True
        if CONFIG["download_cover"]:
            self.download_cover()
        if CONFIG["download_lyric"]:
            self.download_lyric()
        self.download_mp3()
        self.song.remove_lock = False
        self.callback()

    def get_safe_path(self, url):
        not_safe_chars = '''\/:*?<>|'"'''
        if len(url) > 243:
            url = url[:238]
        for char in not_safe_chars:
            url = url.replace(char, "")
        return url

    def get_filepath(self):
        download_folder = CONFIG["download_folder"]
        if download_folder.endswith("/"):
            download_folder = download_folder[:-1]
        filename = CONFIG["filename_template"].replace("${ALBUM}", self.song.album_name)
        filename = filename.replace("${ARTIST}", self.song.artist_name)
        filename = filename.replace("${TITLE}", self.get_safe_path(self.song.name))
        if "${TRACK}" in filename:
            filename = filename.replace("${TRACK}", self.song.providerId[-2:])
        filepath = "%s/%s.mp3" % (download_folder, filename)
        return filepath

    def download_cover(self):
        self.song.down_status = "正在获取封面地址"
        if self.song.cover_url == "":
            self.song.down_status = "获取封面地址失败"
            return

        filepath = "%s/cover.jpg" % os.path.dirname(self.get_filepath())

        if os.path.exists(filepath):
            self.song.down_status = "封面已存在"
            return

        if not os.path.exists(os.path.dirname(filepath)):
            os.makedirs(os.path.dirname(filepath))

        try:
            self.song.down_status = "下载封面中"
            urllib.urlretrieve(self.song.cover_url, filepath)
            self.song.down_status = "下载封面完成"
        except:
            traceback.print_exc()

    def download_lyric(self):
        self.song.down_status = "正在获取歌词地址"
        self.song.load_song_link()
        if self.song.lyric_url == "":
            self.song.down_status = "获取歌词地址失败"
            return

        # remove ".mp3" extension
        filepath = "%s.lrc" % self.get_filepath()[:-4]

        if os.path.exists(filepath):
            self.song.down_status = "歌词文件已存在"
            return

        if not os.path.exists(os.path.dirname(filepath)):
            os.makedirs(os.path.dirname(filepath))

        try:
            self.song.down_status = "下载歌词中"
            urllib.urlretrieve(self.song.lyric_url, filepath)
            self.song.down_status = "下载歌词完成"
        except:
            traceback.print_exc()

    def download_mp3(self):
        self.song.down_status = "正在获取地址"
        self.song.load_song_link()
        if not self.song.download_url:
            self.song.down_status = "获取地址失败"
            return

        filepath = self.get_filepath()

        if os.path.exists(filepath):
            self.song.down_status = "文件已存在"
            self.song.down_process = "100%"
            return

        if not os.path.exists(os.path.dirname(filepath)):
            os.makedirs(os.path.dirname(filepath))

        download_url = self.song.download_url[0][0]      #TODO: 修改download_url
        try:
            self.song.down_status = "下载中"
            urllib.urlretrieve(download_url, filepath, self.process)
            self.song.down_status = "下载完成"
        except:
            traceback.print_exc()

    def process(self, block, block_size, total_size):
        downloaded_size = block * block_size
        percent = float(downloaded_size) / total_size
        if percent >= 1:
            process = "100%"
        elif percent <= 0:
            process = "0%"
        elif percent < 0.1:
            process = str(percent)[3:4] + "%"
        else:
            process = str(percent)[2:4] + "%"
        self.song.down_process = process
        
class Cacher(threading.Thread):
    def __init__(self, song):
        threading.Thread.__init__(self)
        self.song = song
    
    def run(self):
        self.song.remove_lock = True
        self.make_cache()
        self.song.remove_lock = False
        
    def get_cachepath(self):
        cache_folder = CONFIG["cache_music_folder"]
        cache_name = CONFIG['cache_music_template'].replace("${ID}", self.song.id)
        cache_path = "%s/%s.mp3" % (cache_folder, cache_name)
        return cache_path
    
    def make_cache(self):
        cache_path = self.get_cachepath()
        if not os.path.exists(cache_path):
            download_url = self.song.download_url[0][0]      #TODO: 修改download_url
            try:
                urllib.urlretrieve(download_url, cache_path)
                self.song.local_path = cache_path
            except:
                traceback.print_exc()
                return
        self.song.local_path = cache_path
