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

import xml.dom.minidom as minidom
import logging
import hashlib
import urllib2
import re
from abc import ABCMeta, abstractmethod
from bs4 import BeautifulSoup

def get_logger(logger_name):
    ''' 获得一个logger '''
    format = '%(asctime)s %(levelname)s %(message)s'
    #level = logging.DEBUG
    level = logging.WARNING
    logging.basicConfig(format=format, level=level)
    logger = logging.getLogger(logger_name)
    return logger

logger = get_logger('googlemusic')

class GmObject(object):
    '''gmbox基本类

    定义共享工具类型的方法，子类实现具体方法。
    '''

    def __init__(self):
        self.gmattrs = {}

    def parse_node(self, node):
        '''解析xml节点添加实例属性'''

        for childNode in node.childNodes:
            name = childNode.tagName
            if childNode.hasChildNodes():
                value = childNode.childNodes[0].data
            else:
                value = ""
            self.gmattrs[name] = value
            setattr(self, name, value)

    def parse_dict(self, dict):
        '''解析dict键值添加实例属性'''

        for key, value in dict.iteritems():
            self.gmattrs[key] = value
            setattr(self, key, value)

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
    
class SidebarList(object):
    '''侧边栏列表基类'''
    
    __metaclass__ = ABCMeta
    
    def __init__(self, url):
        self.dict = {}
        self.url = url
    
    def load_list(self):
        pass

class Song(GmObject):
    '''歌曲类'''

    def __init__(self, relative_url = None):
        GmObject.__init__(self)
        if relative_url is not None:
            self.url = 'http://music.baidu.com%s' % relative_url
            pos = self.url.rfind('/')
            self.id = self.url[pos + 1 : -1]
            info_dict = self.load_detail()
            self.parse_dict(info_dict)
            
        
    def load_artist(self, soup):
        artist_detail = soup.find('a', href = re.compile('artist'))
        artist_soup = BeautifulSoup(repr(artist_detail))
        artist_dict = {}
        artist_dict.setdefault(artist_soup.text.lstrip().rstrip(), artist_soup.a['href'])
        return artist_dict
        
    
    def load_album(self, soup):
        album_detail = soup.find('a', href = re.compile('album'))
        album_dict = {}
        if album_detail:
            album_soup = BeautifulSoup(repr(album_detail))
            album_dict.setdefault('album_url', album_soup.a['href'])
            album_dict.setdefault('album_name', album_soup.text.lstrip().rstrip())
        else:
            album_dict.set_default('album_url', "")
            album_dict.set_default('album_name', "")
        return album_dict
    
#     def load_mv(self, soup):
#         album_detail = soup.find('a', href = re.compile('mv'))
#         album_soup = BeautifulSoup(repr(album_detail))
#     
#     def load_tags(self, soup):
#         tags_detail = soup.find('a', attrs = {'class' : 'tag-list'})
#         tags_soup = BeautifulSoup(repr(tags_detail))
#     
#     def load_lyric(self, soup):
#         lyric_detail = soup.find('a', attrs = {'data-lyricdata' : True})
#         lyric_soup = BeautifulSoup(repr(lyric_detail))
    
    def load_download_url(self, soup):
        url_detail = soup.find('a', attrs = {'download_url' : True})
        download_reg = re.compile(r'<a .*?download_url="(.+?)".*?</a>', re.S)
        match = download_reg.search(repr(url_detail))
        url_dict = {}
        if match:
            url_dict.setdefault('download_url', match.group(1))
        return url_dict

    def load_detail(self):
        '''读取详情数据
        详情数据是包含艺术家编号，封面地址等数据。
        调用这个函数会发出一个http请求，但只会发出一次，
        亦即数据已经读取了就不再发出http请求了。
        '''
        #fetch album cover url, album info, lyric url, download url, each size of every type
        content = urllib2.urlopen(self.url).read()
        soup = BeautifulSoup(content)
        song_info = soup.find('div', attrs = {'class' : 'song-info'})
        #lyric_info = soup.find('div', attrs= {'class' : 'song-lyric'})
        song_soup = BeautifulSoup(repr(song_info))
        #lyric_soup = BeautifulSoup(repr(lyric_info))
        info_dict = {}
        if not hasattr(self, 'artists'):
            artist_dict = self.load_artist(song_soup)
            info_dict.setdefault('artists', artist_dict)
        if not hasattr(self, 'album_name'):
            album_dict = self.load_album(song_soup)
            info_dict.update(album_dict)
        if not hasattr(self, 'download_url'):
            download_dict = self.load_download_url(song_soup)
            info_dict.update(download_dict)
#         if not hasattr(self, 'lyric'):
#             self.load_lyric(lyric_soup)
#         if not hasattr(self, 'tags'):
#             self.load_tags(song_soup)
#         if not hasattr(self, 'mv'):
#             self.load_mv(song_soup)
        
        return info_dict
            

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
    
    def parse_detail(self, detail):
        if detail.find('song') != -1:
            song_reg = re.compile(r'<a href="(.+?)" title="(.+?)">.*?</a>', re.S)
            match = song_reg.search(detail)
            if match:
                return 'song', match.group(1), match.group(2)
        elif detail.find('artist') != -1:
            artist_reg = re.compile(r'<a .*?href="(.+?)">\s*?(.+?)\s*?</a>', re.S)
            match = artist_reg.search(detail)
            if match:
                return 'artist', match.group(1), match.group(2).lstrip()
        elif detail.find('album') != -1:
            album_reg = re.compile(r'<a href="(.+?)".*?>.*?</a>', re.S)
            match = album_reg.search(detail)
            if match:
                return 'album', match.group(1)
        
    def parse_html(self, html, type, start = 0, count = 20):
        if type == 'chart':
            soup = BeautifulSoup(html)
            item_list = soup.find_all('div', attrs = {'class' : 'song-item'}, limit = count)
            for item in item_list:
                detail_soup = BeautifulSoup(repr(item)) 
                song_dict = {}
                sub_dict = {}  
                detail_list = detail_soup.find_all('a', attrs = {'class' : False})
                for detail in detail_list:
                    detail_tuple = self.parse_detail(repr(detail))
                    if detail_tuple:
                        if detail_tuple[0] == 'album':
                            song_dict.setdefault('album_url', detail_tuple[1])
                        elif detail_tuple[0] == 'song':
                            song_dict.setdefault('song_url', detail_tuple[1])
                            song_dict.setdefault('song_name', detail_tuple[2])
                        elif detail_tuple[0] == 'artist':
                            sub_dict.setdefault(detail_tuple[2], detail_tuple[1])
                if sub_dict:
                    song_dict.setdefault('artists', sub_dict)
                if dict:
                    song = Song(song_dict['song_url'])
                    song.parse_dict(song_dict)
                    self.songs.append(song)

class TagList(SidebarList):
    def __init__(self, url):
        SidebarList.__init__(self, url)
        
    def load_list(self):
        try:
            text = urllib2.urlopen(self.url).read()
            tag_reg = re.compile(r'<dl class="tag-mod" .*?>(.*?)</dl>', re.S)
            groups = re.findall(tag_reg, text)
            
            for item in groups:
                header_reg = re.compile(r'<dt><div>(.*?)</div></dt>')
                item_reg = re.compile(r'<span class="tag-list clearfix">.*?<a href="(.*?)" class=.*?>(.*?)</a>.*?</span>', re.S)
                
                header_groups = re.findall(header_reg, item)
                item_groups = re.findall(item_reg, item)
                subdict = {}
                
                for tag in item_groups:
                    subdict.setdefault(tag[1], tag[0])
                self.dict.setdefault(GmObject.decode_html_text(header_groups[0]), subdict)
                
        except urllib2.HTTPError, he:
            logger.error('Load tag failed!\n\tReason: %s' % he)
            
class StyleList(SidebarList):
    
    def __init__(self, url):
        SidebarList.__init__(self, url)
 
    def load_list(self):
        text = urllib2.urlopen(self.url).read()
        block_reg = re.compile(r'<div .*?class="mod-style.*?>(.+?)</div>',re.S)
        style_reg = re.compile(r'<a href="(.+?)">(.+?)</a>', re.S)
        block_groups = re.findall(block_reg, text)
        for block in block_groups:
            style_groups = re.findall(style_reg, block)
            for style in style_groups:
                self.dict.setdefault(style[1], style[0])

class ChartList(SidebarList):
    
    def __init__(self, url):
        SidebarList.__init__(self, url)

 
    def load_list(self):
        text = urllib2.urlopen(self.url).read()
        head_reg = re.compile(r'<div class="head">(.+?)</div>',re.S)
        url_reg = re.compile(r'<a .*?href="(.+?)".*?>.*?</a>', re.S)
        name_reg = re.compile(r'<h2 class=.+?>(.+?)</h2>')
        head_groups = re.findall(head_reg, text)
        
        for head in head_groups:
            url = url_reg.search(head)
            name = name_reg.search(head)
            self.dict.setdefault(name.group(1), url.group(1))
            
class ArtistList(SidebarList):
    def __init__(self, url):
        SidebarList.__init__(self, url)
        
    def load_list(self):
        text = urllib2.urlopen(self.url).read()
        #list_reg = re.compile(r'<li class="list-item">(.*?)</ul>\s*?</li>',re.S)
        tree_reg = re.compile(r'<dl class="tree_main">(.+?)</dl>', re.S)
        tree_groups = re.findall(tree_reg, text)
        for tree in tree_groups:
            clsfy_reg = re.compile(r'<dt>(.+?)</dt>', re.S)
            item_reg = re.compile(r'<dd >\s*?<a href="(.+?)">(.+?)</a>\s*?</dd>')
            clsfy = re.search(clsfy_reg, tree)
            item_groups = re.findall(item_reg, tree)
            sub_dict = {}
            for item in item_groups:
                sub_dict.setdefault(item[1].decode('utf-8'), item[0])
            if clsfy:
                self.dict.setdefault(clsfy.group(1), sub_dict)
            else:
                self.dict.setdefault('其他', sub_dict)
        
        
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

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self):
        template = "http://www.google.cn/music/album?id=%s&output=xml"
        url = template % self.id

        logger.info('读取专辑地址：%s', url)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songs = self.parse_xml(xml)
        self.songs.extend(songs)
        return songs

class Search(Songlist):
    '''搜索'''

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self, start=0, number=20):
        template = "http://www.google.cn/music/search?cat=song&q=%s&start=%d&num=%d&output=xml"
        url = template % (self.id, start, number + 1)

        logger.info('读取搜索地址：%s', url)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songs = self.parse_xml(xml)
        if len(songs) == number + 1:
            self.has_more = True
            songs.pop()
        else:
            self.has_more = False
        self.songs.extend(songs)
        return songs

class Topiclisting(Songlist):
    '''专题'''

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self):
        template = "http://www.google.cn/music/topiclisting?q=%s&cat=song&output=xml"
        url = template % self.id

        logger.info('读取专题地址：%s', url)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songs = self.parse_xml(xml)
        self.songs.extend(songs)
        return songs
            
class Chartlisting(Songlist):
    '''排行榜'''

    def __init__(self, url = None):
        Songlist.__init__(self)
        if url is not None:
            self.url = 'http://music.baidu.com%s' % url
            self.load_songs()

    def load_songs(self, start=0, number=20):
        logger.info('读取排行榜地址：%s', self.url)
        content = urllib2.urlopen(self.url).read()
        songs = self.parse_html(content, 'chart')
        
        return songs
        

class ArtistSong(Songlist):
    '''艺术家'''

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self):
        template = "http://www.google.cn/music/artist?id=%s&output=xml"
        url = template % self.id

        logger.info('读取艺术家地址：%s', url)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songs = self.parse_xml(xml, "hotSongs")
        self.songs.extend(songs)
        return songs
    
                  
class Tag(Songlist):
    
    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()
 
    def load_songs(self, start=0, number=20):
        template = "http://www.google.cn/music/tag?q=%s&cat=song&type=songs&start=%d&num=%d"
        url = template % (self.id, start, number + 1)
 
        logger.info('读取标签地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songs = self.parse_html(html)
        if len(songs) == number + 1:
            self.has_more = True
            songs.pop()
        else:
            self.has_more = False
        self.songs.extend(songs)
        return songs

class Screener(Songlist):
    '''挑歌

    args_dict 参数示例，字典类型
    {
        'timbre': '0.5', 
        'date_l': '694195200000', 
        'tempo': '0.5', 
        'date_h': '788889600000', 
        'pitch': '0.5', 
        'artist_type': 'male'
    }
    '''

    def __init__(self, args_dict=None):
        Songlist.__init__(self)
        if args_dict is None:
            self.args_dict = {}
        else:
            self.args_dict = args_dict
        self.load_songs()

    def load_songs(self, start=0, number=20):
        template = "http://www.google.cn/music/songscreen?start=%d&num=%d&client=&output=xml"
        url = template % (start, number + 1)

        logger.info('读取挑歌地址：%s', url)
        request_args = []
        for key, value in self.args_dict.iteritems():
            text = "&%s=%s" % (key, value)
            request_args.append(text)
        url = url + "".join(request_args)
        urlopener = urllib2.urlopen(url)
        xml = urlopener.read()
        songs = self.parse_xml(xml)
        if len(songs) == number + 1:
            self.has_more = True
            songs.pop()
        else:
            self.has_more = False
        self.songs.extend(songs)
        return songs

class Similar(Songlist):
    '''相似歌曲'''

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self):
        template = "http://www.google.cn/music/song?id=%s"
        url = template % self.id

        logger.info('读取相似地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songs = self.parse_html(html)
        self.songs.extend(songs)
        return songs

class Starrecc(Songlist):
    '''大牌私房歌'''

    def __init__(self, id=None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()

    def load_songs(self):
        template = "http://www.google.cn/music/playlist/playlist?id=sys:star_recc:%s&type=star_recommendation"
        url = template % self.id

        logger.info('读取大牌私房歌地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songs = self.parse_html(html)
        self.songs.extend(songs)
        return songs

    def parse_html(self, html):
        ids = []
        matches = re.findall('onclick="window.open([^"]+)"', html)
        for match in matches:
            match = re.search('download.html\?id=([^\\\]+)', urllib2.unquote(match)).group(1)
            ids.append(match)

        names = []
        artists = []
        matches = re.findall('<td class="Title"><a .+?>《(.+?)》\n&nbsp;(.+?)</a></td>', html, re.DOTALL)
        for match in matches:
            name = GmObject.decode_html_text(match[0])
            artist = GmObject.decode_html_text(match[1])
            names.append(name)
            artists.append(artist)

        songs = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "artist":artists[i]}
            song = Song()
            song.parse_dict(dict)
            songs.append(song)
        return songs

class Directory(GmObject):
    '''歌曲列表列表基本类，是歌曲列表(Songlist类）的集合，这里简称为“目录”

    类结构和Songlist相同，提供通用的解析方法，特殊情况由子类覆盖方法实现。
    '''

    def __init__(self):
        self.songlists = []
        self.has_more = False

    def load_songlists(self, start=0, number=20):
        '''读取目录里的歌曲列表，子类应覆盖这个方法

        原理类似Songlist类的load_songs方法，请参考该类注释，只不过Songlist类
        实用self.songs而这个类使用self.songlists。
        '''

        pass

class DirSearch(Directory):
    '''专辑搜索'''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def load_songlists(self, start=0, number=20):
        template = "http://www.google.cn/music/search?q=%s&cat=album&start=%d&num=%d"
        url = template % (self.id, start, number + 1)

        logger.info('读取专辑搜索地址：%s', url)
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
        ids = []
        matches = re.findall('<!--freemusic/album/result/([^-]+)-->', html)
        for match in matches:
            ids.append(match)

        names = []
        matches = re.findall('《(.+)》', html)
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

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "artist":artists[i], "thumbnailLink":thumbnails[i]}
            album = Album()
            album.parse_dict(dict)
            songlists.append(album)
        return songlists

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

        # WorkAround
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

        # 某些专辑没有封面，则使用默认
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
        # 上面的的正则表达式同样匹配艺术家头像，位置在第一，所以要去掉。
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
