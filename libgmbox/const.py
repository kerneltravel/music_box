#!/usr/bin/env python
# -*- coding: utf-8 -*-

__doc__ = '''gmbox常量文件

这个文件定义了gmbox核心库使用的常量，可能需要定时更新。
'''

ARTIST = {
          "华语":[
                ("华语男歌手", "cn/male"),
                ("华语女歌手", "cn/female"),
                ("华语乐队组合", "cn/group")
                ],
          "欧美":[
                ("欧美男歌手", "western/male"),
                ("欧美女歌手", "western/female"),
                ("欧美乐队组合", "western/group")],
          "日韩":[
                ("日韩男歌手", "jpkr/male"),
                ("日韩女歌手", "jpkr/female"),
                ("日韩乐队组合", "jpkr/group")],
          "其他":[
                ("其他歌手", "other")]
}

GENRES = [
    ("摇滚", 'style_rock'),
    ("民谣", 'style_folk'),
    ("流行", 'style_pop'),
    ("乡村", 'style_country'),
    ("嘻哈", 'style_hiphop'),
    ("爵士", 'style_jazz'),
    ("电子", 'style_elc'),
    ("节奏布鲁斯", 'style_blues')
]

CHARTLISTING_DIR = {"主打榜单": [
                             ("热歌榜 TOP500", "dayhot"),
                             ("新歌榜 TOP100", "new"),
                             ("歌手榜 TOP200", "artist")
                             ],
                    "分类榜单": [
                             ("中国好声音榜", "chinavoice2013"),
                             ("欧美金曲榜", "oumei"),
                             ("影视金曲榜", "yingshijinqu"),
                             ("情歌对唱榜", "lovesong"),
                             ("网络歌曲榜", "netsong"),
                             ("经典老歌榜", "oldsong"),
                             ("摇滚榜", "rock")
                             ],
                    "媒体榜单": [
                             ("KTV热歌榜", "ktv"), 
                             ("Billboard", "billboard"),
                             ("UK Chart", "ukchart"),
                             ("Hito中文榜", "hito"),
                             ("叱咤歌曲榜", "chizha")
                             ]
}

TAG_DIR = [
           "热门标签",
           "音乐心情",
           "年代",
           "主题",
           "风格",
           "场景",
           "语言&地域",
           "乐器&音色"     
]
