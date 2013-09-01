#!/usr/bin/env python
# -*- coding: utf-8 -*-

__doc__ = '''gmbox核心库

这个库复制解析请求结果，并把结果转换为python对象。

基本对象：
Song: 歌曲
Songlist: 包含Song类的列表，子类是专辑、歌曲排行榜等。
Directory: 包含Songlist类（或子类）的列表，子类是搜索专辑，专辑排行榜等。

解析结果：
谷歌音乐的某些结果提供xml，通过它的flash播放器抓包分析所得。
某些功能没有xml，只好解析html，理论上解析速度会比xml慢。
'''

import logging
import urllib2
import urllib
import re
import sys
from threading import Thread
import Queue
from bs4 import BeautifulSoup
import json

def get_logger(logger_name):
    ''' 获得一个logger '''
    format = '%(asctime)s %(levelname)s %(message)s'
    #level = logging.DEBUG
    level = logging.WARNING
    logging.basicConfig(format=format, level=level)
    logger = logging.getLogger(logger_name)
    return logger

logger = get_logger('baidumusic')

class GmObject(object):
    '''gmbox基本类

    定义共享工具类型的方法，子类实现具体方法。
    '''

    def __init__(self):
        self.gmattrs = {}

    def parse_dict(self, dict):
        '''解析dict键值添加实例属性'''

        for key, value in dict.iteritems():
            if not hasattr(self, key):
                self.gmattrs[key] = value
                setattr(self, key, value)
                
    def get_request(self, url):
        req = urllib2.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        return req

    @staticmethod
    def decode_html_text(text):
        '''转义html特殊符号'''

        html_escape_table = {
            "&nbsp;" : " ",
            "&quot;" : '"',
            "&ldquo;" : "“",
            "&rdquo;" : "”",
            "&mdash;" : "—",
            "&amp;" : "&",
            "&middot;" : "·"
        }
        for key, value in html_escape_table.iteritems():
            text = text.replace(key, value)
        numbers = re.findall('&#([^;]+);', text)
        for number in numbers:
            text = text.replace("&#%s;" % number, unichr(int(number)))
        return text
    
def handle_exception(func):
    def _wrapper(*args, **kwargs):
        try:
            func(args, kwargs)
        except urllib2.HTTPError, he:
            logger.error('Load tag failed!\n\tReason: %s' , he)
        except urllib2.URLError, ue:
            logger.error('Open url failed!\n\tReason: %s' , ue)
        return _wrapper
        
    
class SidebarList(object):
    '''侧边栏列表基类'''
    
    def __init__(self, url):
        self.dict = {}
        self.url = url
        self.req = urllib2.Request(self.url)
        self.req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        self.loaded = False
    
    def load_list(self):
        pass
    
class QueryThread(Thread):
    thread_id = 0
      
    def __init__(self, work_queue, *args, **key_args):
        Thread.__init__(self, **key_args)
        self.id = QueryThread.thread_id
        QueryThread.thread_id += 1
        self.setDaemon(True)
        self.work_queue = work_queue
        self.state = 'READY'
        self.start()
        
    def run(self):
        while True:
            if self.state == 'STOP':
                break
            try:
                func, args, key_args = self.work_queue.get()
            except Queue.Empty:
                continue
            
            try:
                func(*args, **key_args)
                self.work_queue.task_done()
            except:
                print sys.exc_info()
                break
            
    def stop(self):
        self.state = 'STOP'
    
class QueryPool(object):
    
    def __init__(self, size = 8):
        self.size = size
        self.queue = Queue.Queue()
        self.threads = []
        self._spawn_threads()
    
    def _spawn_threads(self):
        ix = 0
        while ix < self.size:
            t = QueryThread(self.queue)
            self.threads.append(t)
            ix += 1
            
    def join_threads(self):
        self.queue.join()
        
    def add_job(self, func, *args, **key_args):
        self.queue.put((func, args, key_args))
        
    def stop_threads(self):
        for item in self.threads:
            item.stop()
        del self.threads[:]   
        
class SongSet(GmObject):
    
    def __init__(self, sid_list = None):
        GmObject.__init__(self) 
        self.songs = []
        
        self.id_list = [ str(item) for item in sid_list]
        self.query_url = 'http://play.baidu.com/data/music/songinfo?songIds=%s' % ','.join(self.id_list)
        self.query_req = urllib2.Request(self.query_url)
        self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        
        self.load_songs_info()
        
    def process_artist(self, name_list, id_list):
        artists = []
        for aname, aid in zip(name_list, id_list):
            artists.append([aid, aname])
        return artists
    
    def parse_info(self, info_dict):
        try:
            attr_dict = {}
            attr_dict.setdefault('name', info_dict['songName'])
            attr_dict.setdefault('id', info_dict['songId'])
            
            name_list = info_dict['artistName'].split(',')
            id_list = repr(info_dict['artistId']).split(',')
            artist_list = self.process_artist(name_list, id_list)
            attr_dict.setdefault('artist_list', artist_list)
            name_list = []
            for item in artist_list:
                name_list.append(item[1])
            artist_name = '&'.join(name_list)
            attr_dict.setdefault('artist_name', artist_name)
            
            attr_dict.setdefault('album_id', info_dict['albumId'])
            attr_dict.setdefault('album_name', info_dict['albumName'])
            attr_dict.setdefault('cover_url', info_dict['songPicBig'])
            
            return attr_dict
        except IndexError:
            return {}
        
    def load_songs_info(self):
        song_info = urllib2.urlopen(self.query_req).read()
        info_list = json.loads(song_info)['data']['songList']
        
        for item in info_list:
            attr_dict = self.parse_info(item)
            song = Song(attr_dict['id'])
            song.parse_dict(attr_dict)
            self.songs.append(song)

class Song(GmObject):
    '''歌曲类'''

    def __init__(self, sid = None):
        GmObject.__init__(self)
        if sid is not None:
            self.id = sid
                      
            self.link_url = 'http://play.baidu.com/data/music/songlink/?songIds=%s&hq=1&type=mp3' % self.id
            self.link_req = urllib2.Request(self.link_url)
            self.link_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.link_dict = {}
    
    def get_listen_url(self):
        rate_dict = self.link_dict['linkinfo']
        self.download_url = []
        if rate_dict is None:
            self.listen_url = self.link_dict['songLink']
            self.download_url = self.listen_url
            self.duration = self.link_dict['time']
        else:
            min_rate = 65535
            for key in rate_dict:
                rate = int(key)
                self.download_url.append((rate_dict[key]['songLink'], rate_dict[key]['size'], rate_dict[key]['time']))
                if rate < min_rate:
                    min_rate = rate
            min_rate = str(min_rate)
            self.listen_url = rate_dict[min_rate]['songLink']
            self.duration = rate_dict[min_rate]['time']
                 
    def load_song_link(self):
        if not hasattr(self, 'lyric_url') or not hasattr(self, 'link_dict'):
            song_link = urllib2.urlopen(self.link_req).read()
            link_dict = json.loads(song_link)
            self.link_dict = link_dict['data']['songList'][0]
            self.lyric_url = 'http://music.baidu.com%s' % self.link_dict['lrcLink']
            self.get_listen_url()

        
    def load_detail(self):
        '''读取详情数据
        详情数据是包含艺术家编号，封面地址等数据。
        调用这个函数会发出一个http请求，但只会发出一次，
        亦即数据已经读取了就不再发出http请求了。
        '''
        info_dict = self.load_song_info()
        self.parse_dict(info_dict)
            

class Songlist(GmObject):
    '''歌曲列表基本类，是歌曲(Song类）的集合

    定义共享解析的方法，分别是xml和html，部分内容可能没有xml提供。
    对于特别的情况，由子类覆盖方法实现。

    '''

    def __init__(self):
        GmObject.__init__(self)
        self.songs = []
        self.has_more = False

    def load_songs(self):
        '''读取歌曲列表里的歌曲，子类应覆盖这个方法

        调用self.load_songs后，self.songs会保存了本次请求的Song类的实例，
        例如：
        第一次调用self.load_songs后，self.songs只包含第一页的20首歌曲
        第二次调用self.load_songs后，self.songs只包含第二页的20首歌曲
        余下同理。

        所以请先从self.songs复制出Song实例后再调用self.load_songs，以免
        前面的结果被覆盖。
        可以检查self.has_more是否还有更多，亦即是否存在下一页。
        '''

        pass
    
    def load_more(self, page = 1, count = 20):
        
        pass

# class TagList(SidebarList):
#     def __init__(self, url):
#         SidebarList.__init__(self, url)
#         
#     @handle_exception
#     def load_list(self):
#         text = urllib2.urlopen(self.req).read()
#         tag_reg = re.compile(r'<dl class="tag-mod" .*?>(.*?)</dl>', re.S)
#         groups = re.findall(tag_reg, text)
#             
#         for item in groups:
#             header_reg = re.compile(r'<dt><div>(.*?)</div></dt>')
#             item_reg = re.compile(r'<span class="tag-list clearfix">.*?<a href="(.*?)" class=.*?>(.*?)</a>.*?</span>', re.S)
#                 
#             header_groups = re.findall(header_reg, item)
#             item_groups = re.findall(item_reg, item)
#             subdict = {}
#                 
#             for tag in item_groups:
#                 subdict.setdefault(tag[1], tag[0])
#             self.dict.setdefault(GmObject.decode_html_text(header_groups[0]), subdict)
#         self.loaded = True
#                 
#         list_groups = re.findall(list_reg,text)
#         for item in list_groups:
#             name_reg = re.compile(r'<h3><a name="\w*?"></a>(.*?)</h3>', re.S)
#             names = re.search(name_reg, item)
#             artist_reg = re.compile(r'(?:<dd|<li)\s*?>\s*?<a href="(.+?)" title="(.+?)".*?>.+?</a>\s*?(?:</dd>|</li>)', re.S)
#             artist_groups = re.findall(artist_reg, item)
#             sub_dict = {}
#             for artist in artist_groups:
#                 sub_dict.setdefault(artist[1].decode('utf-8'), artist[0])
#             if names.group(1):
#                 self.dict.setdefault(names.group(1), sub_dict)
    
class Album(Songlist):
    '''专辑'''

    def __init__(self, id = None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            template = "http://play.baidu.com/data/music/box/album?albumId=%s&type=album"
            url = template % self.id
            self.req = self.get_request(url)
            self.load_songs()

    
    def load_detail(self, info_dict):
        attr_dict = {}
        attr_dict.setdefault('cover_url', info_dict['data']['albumPicSmall'])
        attr_dict.setdefault('name', info_dict['data']['albumName'])
        attr_dict.setdefault('artists', [[0 ,info_dict['data']['artistName']]])
        
        self.parse_dict(attr_dict)
        
    def load_songs(self):
        info_dict = json.loads(urllib2.urlopen(self.req).read())
        self.load_detail(info_dict)
        
        id_list = info_dict['data']['songIdList']
        song_set = SongSet(id_list)
        self.songs.extend(song_set.songs)
        
        return self.songs

class Search(Songlist):
    '''搜索'''
#http://music.baidu.com/data/user/getsongs?start=0&ting_uid=7994&order=hot    artist - song
#http://music.baidu.com/data/user/getalbums?start=10&ting_uid=7994&order=time    artist - album
    def __init__(self, id = None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()
            
    def add_songs(self, content, count):
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        id_list = song_reg.findall(content)
        if len(id_list) == count:
            self.has_more = True
        else:
            self.has_more = False
        song_set = SongSet(id_list)
        songs = song_set.songs
        
        return songs

    def load_songs(self, start = 0, count = 20):
        template = "http://music.baidu.com/search/song?key=%s&start=%d&size=%d"
        url = template % (self.id, start, count)
        
        logger.info('读取搜索地址：%s', url)
        req = urllib2.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        content = urllib2.urlopen(req).read()
        
        songs = self.add_songs(content, count)
        self.songs.extend(songs)
        return songs
    
    def load_more(self, page = 1, count = 20):
        start = page * count
        return self.load_songs(start, count)

# class Topiclisting(Songlist):
#     '''专题'''
# 
#     def __init__(self, id = None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/topiclisting?q=%s&cat=song&output=xml"
#         url = template % self.id
# 
#         logger.info('读取专题地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         xml = urlopener.read()
#         songs = self.parse_xml(xml)
#         self.songs.extend(songs)
#         return songs
            
class Chartlisting(Songlist):
    def __init__(self, top_id = None):
        Songlist.__init__(self)
        self.songs = []
        if top_id is not None:
            query_url = 'http://play.baidu.com/data/music/box/top?topId=%s' % top_id
            self.query_req = urllib2.Request(query_url)
            self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.load_songs()
        
    def add_songs(self, start, count):
        end = start + count
        if self.unloaded_count > count:
            self.has_more = True
            sub_list = self.id_list[start : end]
            song_set = SongSet(sub_list)
            self.unloaded_count -= count
        else:
            self.has_more = False
            song_set = SongSet(self.id_list)
            self.unloaded_count = 0
        
        return song_set.songs
    
    def load_songs(self, start = 0, count = 20):
        logger.debug('加载排行榜信息...')
        chart_dict = json.loads(urllib2.urlopen(self.query_req).read())
        self.id_list = chart_dict['data']['songIdList']
        
        self.unloaded_count = len(self.id_list)
        songs = self.add_songs(start, count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
        
        return self.songs
        
    def load_more(self, page = 1, count = 20):
        start = (page - 1) * count
        del self.songs[ : ]
        songs = self.add_songs(start, count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
                
        return self.songs
    
class Stylelisting(Songlist):
    def __init__(self, style_id = None):
        Songlist.__init__(self)
        self.style_id = style_id
        self.songs = []
        if self.style_id is not None:
            query_url = 'http://music.baidu.com/data/genres/getsongs?title=%s' % self.style_id
            self.query_req = urllib2.Request(query_url)
            self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.load_songs()
        
    def add_songs(self, data, count = 20):
        parse_content = urllib2.urlopen(self.query_req, data).read()
        info_dict = json.loads(parse_content)
        html = info_dict['data']['html']
        error_code = json.loads(parse_content)['errorCode']
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        if error_code != 22000:
            self.has_more = False
        id_list = song_reg.findall(html)
        if len(id_list) == count:
            self.has_more = True
        else:
            self.has_more = False
            
        song_set = SongSet(id_list)
        songs = song_set.songs
        
        return songs
    
    
    def load_songs(self, start = 0, count = 20):
        logger.debug('加载流派-%s信息...', self.style_id)
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        self.songs.extend(songs)
        
        return songs
        
        
    def load_more(self, page = 1, count = 20):
        start = page * count
        del self.songs[ : ]
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
                
        return self.songs
        
# class Taglisting(Songlist):
#     
#     def __init__(self, url = None):
#         Songlist.__init__(self)
#         if url is not None:
#             self.url = 'http://music.baidu.com%s' % url
#             self.load_songs()
#     
#     def load_songs(self, start, number = 20):
#         logger.info('读取标签地址: %s', self.url)
#         content = urllib2.urlopen(self.url).read()
#         songs = self.parse_html(content, 'chart')
#         
#         return songs
        

# class ArtistSong(Songlist):
#     '''艺术家'''
# 
#     def __init__(self, id=None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/artist?id=%s&output=xml"
#         url = template % self.id
# 
#         logger.info('读取艺术家地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         xml = urlopener.read()
#         songs = self.parse_xml(xml, "hotSongs")
#         self.songs.extend(songs)
#         return songs

# class Screener(Songlist):
#     '''挑歌
# 
#     args_dict 参数示例，字典类型
#     {
#         'timbre': '0.5', 
#         'date_l': '694195200000', 
#         'tempo': '0.5', 
#         'date_h': '788889600000', 
#         'pitch': '0.5', 
#         'artist_type': 'male'
#     }
#     '''
# 
#     def __init__(self, args_dict=None):
#         Songlist.__init__(self)
#         if args_dict is None:
#             self.args_dict = {}
#         else:
#             self.args_dict = args_dict
#         self.load_songs()
# 
#     def load_songs(self, start=0, number=20):
#         template = "http://www.google.cn/music/songscreen?start=%d&num=%d&client=&output=xml"
#         url = template % (start, number + 1)
# 
#         logger.info('读取挑歌地址：%s', url)
#         request_args = []
#         for key, value in self.args_dict.iteritems():
#             text = "&%s=%s" % (key, value)
#             request_args.append(text)
#         url = url + "".join(request_args)
#         urlopener = urllib2.urlopen(url)
#         xml = urlopener.read()
#         songs = self.parse_xml(xml)
#         if len(songs) == number + 1:
#             self.has_more = True
#             songs.pop()
#         else:
#             self.has_more = False
#         self.songs.extend(songs)
#         return songs

# class Similar(Songlist):
#     '''相似歌曲'''
# 
#     def __init__(self, id=None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/song?id=%s"
#         url = template % self.id
# 
#         logger.info('读取相似地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         html = urlopener.read()
#         songs = self.parse_html(html)
#         self.songs.extend(songs)
#         return songs
# 
# class Starrecc(Songlist):
#     '''大牌私房歌'''
# 
#     def __init__(self, id=None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/playlist/playlist?id=sys:star_recc:%s&type=star_recommendation"
#         url = template % self.id
# 
#         logger.info('读取大牌私房歌地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         html = urlopener.read()
#         songs = self.parse_html(html)
#         self.songs.extend(songs)
#         return songs
# 
#     def parse_html(self, html):
#         ids = []
#         matches = re.findall('onclick="window.open([^"]+)"', html)
#         for match in matches:
#             match = re.search('download.html\?id=([^\\\]+)', urllib2.unquote(match)).group(1)
#             ids.append(match)
# 
#         names = []
#         artists = []
#         matches = re.findall('<td class="Title"><a .+?>《(.+?)》\n&nbsp;(.+?)</a></td>', html, re.DOTALL)
#         for match in matches:
#             name = GmObject.decode_html_text(match[0])
#             artist = GmObject.decode_html_text(match[1])
#             names.append(name)
#             artists.append(artist)
# 
#         songs = []
#         for i in range(len(ids)):
#             dict = {"id":ids[i], "name":names[i], "artist":artists[i]}
#             song = Song()
#             song.parse_dict(dict)
#             songs.append(song)
#         return songs

class Directory(GmObject):
    '''歌曲列表列表基本类，是歌曲列表(Songlist类）的集合，这里简称为“目录”
 
    类结构和Songlist相同，提供通用的解析方法，特殊情况由子类覆盖方法实现。
    '''
 
    def __init__(self):
        self.songlists = []
        self.has_more = False
 
    def load_songlists(self, start = 0, count = 10):
        '''读取目录里的歌曲列表，子类应覆盖这个方法
 
        原理类似Songlist类的load_songs方法，请参考该类注释，只不过Songlist类
        实用self.songs而这个类使用self.songlists。
        '''
 
        pass
 
class DirSearch(Directory):
    '''专辑搜索'''

    def __init__(self, dir_name):
        Directory.__init__(self)
        self.id = dir_name
        self.load_songlists()

    def load_songlists(self, start = 0, count = 10):
        url = 'http://music.baidu.com/search/album?key=%s&start=%d&size=%d' % (self.id, start, count)
        req = self.get_request(url)
        logger.info('读取专辑搜索地址: %s', url)
        
        content = urllib2.urlopen(req).read()
        album_reg = re.compile(r'<a .*?href="/album/(.+?)" title="\S*".*?>')
        album_list = album_reg.findall(content)
        album_list = list(set(album_list))
        if len(album_list) == count:
            self.has_more = True
        else:
            self.has_more = False
        songlists = []
        for album_id in album_list:
            album = Album(album_id)
            songlists.append(album)
        
        self.songlists.extend(songlists)
        return songlists
    
    def load_more(self, page = 1, count = 10):
        start = page * count
        return self.load_songlists(start, count)

class DirChartlisting(Directory):
    '''专辑排行榜'''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def load_songlists(self, start=0, number=20):
        template = "http://www.google.cn/music/chartlisting?q=%s&cat=album&start=%d&num=%d&output=xml"
        url = template % (self.id, start, number + 1)

        logger.info('读取专辑排行榜地址：%s', url)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songlists = self.parse_xml(xml)
        if len(songlists) == number + 1:
            self.has_more = True
            songlists.pop()
        else:
            self.has_more = False
        self.songlists.extend(songlists)
        return songlists

    def parse_xml(self, xml):
        songlists = []
        dom = minidom.parseString(xml)
        for node in dom.getElementsByTagName("node"):
            if (node.nodeType == node.ELEMENT_NODE):
                album = Album()
                album.parse_node(node)
                songlists.append(album)
        return songlists

class DirTopiclistingdir(Directory):
    '''专辑专题'''

    def __init__(self):
        Directory.__init__(self)
        self.load_songlists()

    def load_songlists(self, start=0, number=20):
        template = "http://www.google.cn/music/topiclistingdir?cat=song&start=%d&num=%d"
        url = template % (start, number + 1)

        logger.info('读取专辑专题地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        if len(songlists) == number + 1:
            self.has_more = True
            songlists.pop()
        else:
            self.has_more = False
        self.songlists.extend(songlists)
        return songlists

    def parse_html(self, html):
        html = urllib2.unquote(html)

        ids = []
        matches = re.findall('<a class="topic_title" href="([^"]+)">', html)
        for match in matches:
            match = re.search('topiclisting\?q=([^&]+)&', urllib2.unquote(match)).group(1)
            ids.append(match)

        names = []
        matches = re.findall('<a class="topic_title" [^>]+>([^<]+)</a>', html)
        for match in matches:
            match = GmObject.decode_html_text(match)
            names.append(match)

        descriptions = []
        matches = re.findall('<td class="topic_description"><div title="([^"]+)"', html)
        for match in matches:
            match = match.split()[0]
            match = GmObject.decode_html_text(match)
            descriptions.append(match)

        #WorkAround
        if len(matches) != len(ids):
            matches = re.findall('<td class="topic_description"><div([^<]+)<', html)
            for match in matches:
                match = match.split()[0]
                match = GmObject.decode_html_text(match)
                if match.startswith(' title="'):
                    match = match[len((' title="')):]
                elif match.startswith('<'):
                    match = match[2:]
                descriptions.append(match)

        thumbnails = []
        for i in range(len(ids)):
            thumbnails.append("http://www.google.cn/music/images/cd_cover_default_big.png")
        matches = re.findall('<td class="td-thumb-big">.+?topiclisting\?q=(.+?)&.+?src="(.+?)"', html, re.DOTALL)
        for match in matches:
            for i in range(len(ids)):
                if match[0] == ids[i]:
                    thumbnails[i] = match[1]

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "descriptions":descriptions[i],
                    "thumbnailLink":thumbnails[i]}
            topiclisting = Topiclisting()
            topiclisting.parse_dict(dict)
            songlists.append(topiclisting)
        return songlists


class DirArtist(Directory):
    '''艺术家搜索'''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def parse_html(self, html):
        html = urllib2.unquote(html)

        ids = []
        matches = re.findall('<!--freemusic/artist/result/([^-]+)-->', html)
        for match in matches:
            ids.append(match)

        names = []
        matches = re.findall('<a href="/music/url\?q=/music/artist\?id.+?>(.+?)</a>', html)
        for match in matches:
            match = match.replace("<b>", "")
            match = match.replace("</b>", "")
            match = GmObject.decode_html_text(match)
            names.append(match)

        thumbnails = []

        #某些专辑没有封面，则使用默认
        for i in range(len(ids)):
            thumbnails.append("http://www.google.cn/music/images/shadow_background.png")
        matches = re.findall('<div class="thumb">.+?artist\?id=(.+?)&.+?src="(.+?)"', html, re.DOTALL)
        for match in matches:
            for i in range(len(ids)):
                if match[0] == ids[i]:
                    thumbnails[i] = match[1]

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "thumbnailLink":thumbnails[i]}
            artist_song = ArtistSong()
            artist_song.parse_dict(dict)
            songlists.append(artist_song)
        return songlists

    def load_songlists(self, start=0, number=20):
        template = "http://www.google.cn/music/search?q=%s&cat=artist&start=%d&num=%d"
        url = template % (self.id, start, number + 1)

        logger.info('读取艺术家搜索地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        if len(songlists) == number + 1:
            self.has_more = True
            songlists.pop()
        else:
            self.has_more = False
        self.songlists.extend(songlists)
        return songlists

class DirArtistAlbum(Directory):
    ''' 艺术家专辑 '''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def parse_html(self, html):

        ids = []
        matches = re.findall('<!--freemusic/album/result/([^-]+)-->', html)
        for match in matches:
            ids.append(match)

        names = []
        matches = re.findall('《(.+)》</a>&nbsp;-&nbsp;', html)
        for match in matches:
            match = match.replace("<b>", "")
            match = match.replace("</b>", "")
            match = GmObject.decode_html_text(match)
            names.append(match)

        artists = []
        matches = re.findall('<td class="Tracks" colspan="10" align="left">(.+?)</td>', html)
        for match in matches:
            match = match.replace("<b>", "")
            match = match.replace("</b>", "")
            match = match.split()[0]
            match = GmObject.decode_html_text(match)
            artists.append(match)

        thumbnails = []
        matches = re.findall('<img [^/]+ class="thumb-img" [^/]+ src="([^"]+)"', html)
        for match in matches:
            thumbnails.append(match)
        #上面的的正则表达式同样匹配艺术家头像，位置在第一，所以要去掉。
        thumbnails = thumbnails[1:]

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "artist":artists[i], "thumbnailLink":thumbnails[i]}
            album = Album()
            album.parse_dict(dict)
            songlists.append(album)
        return songlists

    def load_songlists(self):
        template = "http://www.google.cn/music/artist?id=%s"
        url = template % self.id

        logger.info('读取艺术家专辑地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        self.songlists.extend(songlists)
        return songlists

class DirTag(DirTopiclistingdir):
    '''专辑标签'''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def load_songlists(self, start=0, number=20):
        template = "http://www.google.cn/music/tag?q=%s&cat=song&type=topics&start=%d&num=%d"
        url = template % (self.id, start, number + 1)

        logger.info('读取专辑标签地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        if len(songlists) == number + 1:
            self.has_more = True
            songlists.pop()
        else:
            self.has_more = False
        self.songlists.extend(songlists)
        return songlists

class DirStarrecc(Directory):
    '''大牌私房歌歌手列表'''

    def __init__(self):
        Directory.__init__(self)
        self.load_songlists()

    def load_songlists(self):
        template = "http://www.google.cn/music/starrecommendationdir?num=100"
        url = template

        logger.info('读取大牌私房歌歌手列表地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        self.songlists.extend(songlists)
        return songlists

    def parse_html(self, html):
        html = urllib2.unquote(html)

        ids = []
        names = []
        matches = re.findall('<div class="artist_name"><a .+?sys:star_recc:(.+?)&.+?>(.+?)</a></div>', html)
        for match in matches:
            id = match[0]
            name = GmObject.decode_html_text(match[1])
            ids.append(id)
            names.append(name)

        descriptions = []
        matches = re.findall('<div class="song_count">(.+?)</div>', html, re.DOTALL)
        for match in matches:
            match = GmObject.decode_html_text(match)
            descriptions.append(match)

        thumbnails = []
        matches = re.findall('<div class="artist_thumb">.+?src="(.+?)".+?</div>', html, re.DOTALL)
        for match in matches:
            thumbnails.append(match)

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "descriptions":descriptions[i],
                    "thumbnailLink":thumbnails[i]}
            starrecc = Starrecc()
            starrecc.parse_dict(dict)
            songlists.append(starrecc)
        return songlists
