# app/student/routes.py
import io
import os
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict

import cloudinary
import cloudinary.uploader
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, make_response
from flask_login import login_required, current_user
from fpdf import FPDF
from PIL import Image
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Student, LearningRecord, Staff
from app.decorators import roles_required

student_bp = Blueprint("student", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


# 階層化された地域データ構造 (例として関東地方の一部を定義)
REGION_DATA = {
    "北海道": {
        "北海道": ["赤井川村", "足寄町", "厚岸町", "厚真町", "網走市", "安平町", "池田町", "石狩市", "今金町", "岩内町", "岩見沢市", "歌志内市", "浦河町", "浦幌町", "雨竜町", "江差町", "枝幸町", "江別市", "えりも町", "遠軽町", "遠別町", "恵庭市", "大空町", "奥尻町", "置戸町", "興部町", "長沼町", "長万部町", "小樽市", "音更町", "乙部町", "帯広市", "小平町", "上川町", "上砂川町", "上士幌町", "上富良野町", "神恵内村", "木古内町", "北広島市", "北見市", "喜茂別町", "京極町", "共和町", "清里町", "釧路市", "釧路町", "倶知安町", "栗山町", "黒松内町", "訓子府町", "剣淵町", "小清水町", "札幌市", "更別村", "猿払村", "佐呂間町", "様似町", "砂川市", "標茶町", "標津町", "士別市", "士幌町", "下川町", "積丹町", "斜里町", "白老町", "白糠町", "知内町", "新篠津村", "新得町", "新十津川町", "新冠町", "寿都町", "瀬棚町", "壮瞥町", "大樹町", "鷹栖町", "滝川市", "滝上町", "伊達市", "秩父別町", "千歳市", "月形町", "津別町", "鶴居村", "天塩町", "弟子屈町", "当別町", "当麻町", "洞爺湖町", "苫小牧市", "苫前町", "泊村", "豊浦町", "豊頃町", "豊富町", "奈井江町", "中川町", "中札内村", "中標津町", "中頓別町", "中富良野町", "七飯町", "名寄市", "南幌町", "仁木町", "西興部村", "ニセコ町", "沼田町", "根室市", "登別市", "函館市", "羽幌町", "浜頓別町", "浜中町", "美瑛町", "東神楽町", "東川町", "日高町", "平取町", "比布町", "美唄市", "美深町", "美幌町", "深川市", "福島町", "富良野市", "古平町", "別海町", "北斗市", "幌加内町", "幌延町", "本別町", "幕別町", "増毛町", "真狩村", "松前町", "三笠市", "南富良野町", "むかわ町", "妹背牛町", "森町", "紋別市", "八雲町", "夕張市", "湧別町", "由仁町", "余市町", "羅臼町", "蘭越町", "陸別町", "利尻町", "利尻富士町", "礼文町", "稚内市", "和寒町"]
    },
    "東北": {
        "青森県": ["青森市", "弘前市", "八戸市", "黒石市", "五所川原市", "十和田市", "三沢市", "むつ市", "つがる市", "平川市", "平内町", "今別町", "蓬田村", "外ヶ浜町", "鰺ヶ沢町", "深浦町", "西目屋村", "藤崎町", "大鰐町", "田舎館村", "板柳町", "鶴田町", "中泊町", "野辺地町", "七戸町", "六戸町", "横浜町", "東北町", "六ヶ所村", "おいらせ町", "大間町", "東通村", "風間浦村", "佐井村", "三戸町", "五戸町", "田子町", "南部町", "階上町", "新郷村"],
        "岩手県": ["盛岡市", "宮古市", "大船渡市", "花巻市", "北上市", "久慈市", "遠野市", "一関市", "陸前高田市", "釜石市", "二戸市", "八幡平市", "奥州市", "滝沢市", "雫石町", "葛巻町", "岩手町", "紫波町", "矢巾町", "西和賀町", "金ケ崎町", "平泉町", "住田町", "大槌町", "山田町", "岩泉町", "田野畑村", "普代村", "軽米町", "野田村", "九戸村", "洋野町", "一戸町"],
        "宮城県": ["仙台市", "石巻市", "塩竈市", "気仙沼市", "白石市", "名取市", "角田市", "多賀城市", "岩沼市", "登米市", "栗原市", "東松島市", "大崎市", "富谷市", "蔵王町", "七ヶ宿町", "大河原町", "村田町", "柴田町", "川崎町", "丸森町", "亘理町", "山元町", "松島町", "七ヶ浜町", "利府町", "大和町", "大郷町", "大衡村", "色麻町", "加美町", "涌谷町", "美里町", "女川町", "南三陸町"],
        "秋田県": ["秋田市", "能代市", "横手市", "大館市", "男鹿市", "湯沢市", "鹿角市", "由利本荘市", "潟上市", "大仙市", "北秋田市", "にかほ市", "仙北市", "小坂町", "上小阿仁村", "藤里町", "三種町", "八峰町", "五城目町", "八郎潟町", "井川町", "大潟村", "美郷町", "羽後町", "東成瀬村"],
        "山形県": ["山形市", "米沢市", "鶴岡市", "酒田市", "新庄市", "寒河江市", "上山市", "村山市", "長井市", "天童市", "東根市", "尾花沢市", "南陽市", "山辺町", "中山町", "河北町", "西川町", "朝日町", "大江町", "大石田町", "金山町", "最上町", "舟形町", "真室川町", "大蔵村", "鮭川村", "戸沢村", "高畠町", "川西町", "小国町", "白鷹町", "飯豊町", "三川町", "庄内町", "遊佐町"],
        "福島県": ["福島市", "会津若松市", "郡山市", "いわき市", "白河市", "須賀川市", "喜多方市", "相馬市", "二本松市", "田村市", "南相馬市", "伊達市", "本宮市", "桑折町", "国見町", "川俣町", "大玉村", "鏡石町", "天栄村", "下郷町", "檜枝岐村", "只見町", "南会津町", "北塩原村", "西会津町", "磐梯町", "猪苗代町", "会津坂下町", "湯川村", "柳津町", "三島町", "金山町", "昭和村", "会津美里町", "西郷村", "泉崎村", "中島村", "矢吹町", "棚倉町", "矢祭町", "塙町", "鮫川村", "石川町", "玉川村", "平田村", "浅川町", "古殿町", "三春町", "小野町", "広野町", "楢葉町", "富岡町", "川内村", "大熊町", "双葉町", "浪江町", "葛尾村", "新地町", "飯舘村"]
    },
    "関東": {
        "茨城県": ["水戸市", "日立市", "土浦市", "古河市", "石岡市", "結城市", "龍ケ崎市", "下妻市", "常総市", "常陸太田市", "高萩市", "北茨城市", "笠間市", "取手市", "牛久市", "つくば市", "ひたちなか市", "鹿嶋市", "潮来市", "守谷市", "常陸大宮市", "那珂市", "筑西市", "坂東市", "稲敷市", "かすみがうら市", "桜川市", "神栖市", "行方市", "鉾田市", "つくばみらい市", "小美玉市", "茨城町", "大洗町", "城里町", "東海村", "大子町", "美浦村", "阿見町", "河内町", "八千代町", "五霞町", "境町", "利根町"],
        "栃木県": ["宇都宮市", "足利市", "栃木市", "佐野市", "鹿沼市", "日光市", "小山市", "真岡市", "大田原市", "矢板市", "那須塩原市", "さくら市", "那須烏山市", "下野市", "上三川町", "益子町", "茂木町", "市貝町", "芳賀町", "壬生町", "野木町", "塩谷町", "高根沢町", "那須町", "那珂川町"],
        "群馬県": ["前橋市", "高崎市", "桐生市", "伊勢崎市", "太田市", "沼田市", "館林市", "渋川市", "藤岡市", "富岡市", "安中市", "みどり市", "榛東村", "吉岡町", "上野村", "神流町", "下仁田町", "南牧村", "甘楽町", "中之条町", "長野原町", "嬬恋村", "草津町", "高山村", "東吾妻町", "片品村", "川場村", "昭和村", "みなかみ町", "玉村町", "板倉町", "明和町", "千代田町", "大泉町", "邑楽町"],
        "埼玉県": ["さいたま市", "川越市", "熊谷市", "川口市", "行田市", "秩父市", "所沢市", "飯能市", "加須市", "本庄市", "東松山市", "春日部市", "狭山市", "羽生市", "鴻巣市", "深谷市", "草加市", "越谷市", "蕨市", "戸田市", "入間市", "朝霞市", "志木市", "和光市", "新座市", "桶川市", "久喜市", "北本市", "八潮市", "富士見市", "三郷市", "蓮田市", "坂戸市", "幸手市", "鶴ヶ島市", "日高市", "吉川市", "ふじみ野市", "白岡市", "伊奈町", "三芳町", "毛呂山町", "越生町", "滑川町", "嵐山町", "小川町", "川島町", "吉見町", "鳩山町", "ときがわ町", "横瀬町", "皆野町", "長瀞町", "小鹿野町", "東秩父村", "美里町", "神川町", "上里町", "寄居町", "宮代町", "杉戸町", "松伏町"],
        "千葉県": ["千葉市", "銚子市", "市川市", "船橋市", "館山市", "木更津市", "松戸市", "野田市", "茂原市", "成田市", "佐倉市", "東金市", "旭市", "習志野市", "柏市", "勝浦市", "市原市", "流山市", "八千代市", "我孫子市", "鴨川市", "鎌ケ谷市", "君津市", "富津市", "浦安市", "四街道市", "袖ケ浦市", "八街市", "印西市", "白井市", "富里市", "南房総市", "匝瑳市", "香取市", "山武市", "いすみ市", "大網白里市", "酒々井町", "栄町", "神崎町", "多古町", "東庄町", "九十九里町", "芝山町", "横芝光町", "一宮町", "睦沢町", "長生村", "白子町", "長柄町", "長南町", "大多喜町", "御宿町", "鋸南町"],
        "東京都": ["千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区", "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区", "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区", "八王子市", "立川市", "武蔵野市", "三鷹市", "青梅市", "府中市", "昭島市", "調布市", "町田市", "小金井市", "小平市", "日野市", "東村山市", "国分寺市", "国立市", "福生市", "狛江市", "東大和市", "清瀬市", "東久留米市", "武蔵村山市", "多摩市", "稲城市", "羽村市", "あきる野市", "西東京市", "瑞穂町", "日の出町", "檜原村", "奥多摩町", "大島町", "利島村", "新島村", "神津島村", "三宅村", "御蔵島村", "八丈町", "青ヶ島村", "小笠原村"],
        "神奈川県": ["横浜市", "川崎市", "相模原市", "横須賀市", "平塚市", "鎌倉市", "藤沢市", "小田原市", "茅ヶ崎市", "逗子市", "三浦市", "秦野市", "厚木市", "大和市", "伊勢原市", "海老名市", "座間市", "南足柄市", "綾瀬市", "葉山町", "寒川町", "大磯町", "二宮町", "中井町", "大井町", "松田町", "山北町", "開成町", "箱根町", "真鶴町", "湯河原町", "愛川町", "清川村"]
    },
    "中部": {
        "新潟県": ["新潟市", "長岡市", "三条市", "柏崎市", "新発田市", "小千谷市", "加茂市", "十日町市", "見附市", "村上市", "燕市", "糸魚川市", "妙高市", "五泉市", "上越市", "阿賀野市", "佐渡市", "魚沼市", "南魚沼市", "胎内市", "聖籠町", "弥彦村", "田上町", "阿賀町", "出雲崎町", "湯沢町", "津南町", "刈羽村", "関川村", "粟島浦村"],
        "富山県": ["富山市", "高岡市", "魚津市", "氷見市", "滑川市", "黒部市", "砺波市", "小矢部市", "南砺市", "射水市", "舟橋村", "上市町", "立山町", "入善町", "朝日町"],
        "石川県": ["金沢市", "七尾市", "小松市", "輪島市", "珠洲市", "加賀市", "羽咋市", "かほく市", "白山市", "能美市", "野々市市", "川北町", "津幡町", "内灘町", "志賀町", "宝達志水町", "中能登町", "穴水町", "能登町"],
        "福井県": ["福井市", "敦賀市", "小浜市", "大野市", "勝山市", "鯖江市", "あわら市", "越前市", "坂井市", "永平寺町", "池田町", "南越前町", "越前町", "美浜町", "高浜町", "おおい町", "若狭町"],
        "山梨県": ["甲府市", "富士吉田市", "都留市", "山梨市", "大月市", "韮崎市", "南アルプス市", "北杜市", "甲斐市", "笛吹市", "上野原市", "甲州市", "中央市", "市川三郷町", "早川町", "身延町", "南部町", "富士川町", "昭和町", "道志村", "西桂町", "忍野村", "山中湖村", "鳴沢村", "富士河口湖町", "小菅村", "丹波山村"],
        "長野県": ["長野市", "松本市", "上田市", "岡谷市", "飯田市", "諏訪市", "須坂市", "小諸市", "伊那市", "駒ヶ根市", "中野市", "大町市", "飯山市", "茅野市", "塩尻市", "佐久市", "千曲市", "東御市", "安曇野市", "小海町", "川上村", "南牧村", "南相木村", "北相木村", "佐久穂町", "軽井沢町", "御代田町", "立科町", "青木村", "長和町", "下諏訪町", "富士見町", "原村", "辰野町", "箕輪町", "飯島町", "南箕輪村", "中川村", "宮田村", "松川町", "高森町", "阿南町", "阿智村", "平谷村", "根羽村", "下條村", "売木村", "天龍村", "泰阜村", "喬木村", "豊丘村", "大鹿村", "上松町", "南木曽町", "木祖村", "王滝村", "大桑村", "木曽町", "麻績村", "生坂村", "山形村", "朝日村", "筑北村", "池田町", "松川村", "白馬村", "小谷村", "坂城町", "小布施町", "高山村", "山ノ内町", "木島平村", "野沢温泉村", "信濃町", "小川村", "飯綱町", "栄村",],
        "岐阜県": ["岐阜市", "大垣市", "高山市", "多治見市", "関市", "中津川市", "美濃市", "瑞浪市", "羽島市", "恵那市", "美濃加茂市", "土岐市", "各務原市", "可児市", "山県市", "瑞穂市", "飛騨市", "本巣市", "郡上市", "下呂市", "海津市", "岐南町", "笠松町", "養老町", "垂井町", "関ケ原町", "神戸町", "輪之内町", "安八町", "揖斐川町", "大野町", "池田町", "北方町", "坂祝町", "富加町", "川辺町", "七宗町", "八百津町", "白川町", "東白川村", "御嵩町", "白川村"],
        "静岡県": ["静岡市", "浜松市", "沼津市", "熱海市", "三島市", "富士宮市", "伊東市", "島田市", "富士市", "磐田市", "焼津市", "掛川市", "藤枝市", "御殿場市", "袋井市", "下田市", "裾野市", "湖西市", "伊豆市", "御前崎市", "菊川市", "伊豆の国市", "牧之原市", "東伊豆町", "河津町", "南伊豆町", "松崎町", "西伊豆町", "函南町", "清水町", "長泉町", "小山町", "吉田町", "川根本町", "森町"],
        "愛知県": ["名古屋市", "豊橋市", "岡崎市", "一宮市", "瀬戸市", "半田市", "春日井市", "豊川市", "津島市", "碧南市", "刈谷市", "豊田市", "安城市", "西尾市", "蒲郡市", "犬山市", "常滑市", "江南市", "小牧市", "稲沢市", "新城市", "東海市", "大府市", "知多市", "知立市", "尾張旭市", "高浜市", "岩倉市", "豊明市", "日進市", "田原市", "愛西市", "清須市", "北名古屋市", "弥富市", "みよし市", "あま市", "長久手市", "東郷町", "豊山町", "大口町", "扶桑町", "大治町", "蟹江町", "飛島村", "阿久比町", "東浦町", "南知多町", "美浜町", "武豊町", "幸田町", "設楽町", "東栄町", "豊根村"]
    },
    "近畿": {
        "滋賀県": ["大津市", "彦根市", "長浜市", "近江八幡市", "草津市", "守山市", "栗東市", "甲賀市", "野洲市", "湖南市", "高島市", "東近江市", "米原市", "日野町", "竜王町", "愛荘町", "豊郷町", "甲良町", "多賀町"],
        "京都府": ["京都市", "福知山市", "舞鶴市", "綾部市", "宇治市", "宮津市", "亀岡市", "城陽市", "向日市", "長岡京市", "八幡市", "京田辺市", "南丹市", "木津川市", "京丹後市", "大山崎町", "久御山町", "井手町", "宇治田原町", "笠置町", "和束町", "精華町", "南山城村", "京丹波町", "伊根町", "与謝野町"],
        "大阪府": ["大阪市", "堺市", "岸和田市", "豊中市", "池田市", "吹田市", "泉大津市", "高槻市", "貝塚市", "守口市", "枚方市", "茨木市", "八尾市", "泉佐野市", "富田林市", "寝屋川市", "河内長野市", "松原市", "大東市", "和泉市", "箕面市", "柏原市", "羽曳野市", "門真市", "摂津市", "高石市", "藤井寺市", "東大阪市", "泉南市", "四條畷市", "交野市", "大阪狭山市", "阪南市", "島本町", "豊能町", "能勢町", "忠岡町", "熊取町", "田尻町", "岬町", "太子町", "河南町", "千早赤阪村"],
        "兵庫県": ["神戸市", "姫路市", "尼崎市", "明石市", "西宮市", "洲本市", "芦屋市", "伊丹市", "相生市", "豊岡市", "加古川市", "赤穂市", "西脇市", "宝塚市", "三木市", "高砂市", "川西市", "小野市", "三田市", "加西市", "篠山市", "養父市", "丹波市", "南あわじ市", "朝来市", "淡路市", "宍粟市", "加東市", "たつの市", "猪名川町", "多可町", "稲美町", "播磨町", "市川町", "福崎町", "神河町", "太子町", "上郡町", "佐用町", "香美町", "新温泉町"],
        "奈良県": ["奈良市", "大和高田市", "大和郡山市", "天理市", "橿原市", "桜井市", "五條市", "御所市", "生駒市", "香芝市", "葛城市", "宇陀市", "山添村", "平群町", "三郷町", "斑鳩町", "安堵町", "川西町", "三宅町", "田原本町", "曽爾村", "御杖村", "高取町", "明日香村", "上牧町", "王寺町", "広陵町", "河合町", "吉野町", "大淀町", "下市町", "黒滝村", "天川村", "野迫川村", "十津川村", "下北山村", "上北山村", "川上村", "東吉野村"],
        "和歌山県": ["和歌山市", "海南市", "橋本市", "有田市", "御坊市", "田辺市", "新宮市", "紀の川市", "岩出市", "紀美野町", "かつらぎ町", "九度山町", "高野町", "湯浅町", "広川町", "有田川町", "美浜町", "日高町", "由良町", "印南町", "みなべ町", "日高川町", "白浜町", "上富田町", "すさみ町", "那智勝浦町", "太地町", "古座川町", "北山村", "串本町"]
    },
    "中国": {
        "鳥取県": ["鳥取市", "米子市", "倉吉市", "境港市", "岩美町", "若桜町", "智頭町", "八頭町", "三朝町", "湯梨浜町", "琴浦町", "北栄町", "日吉津村", "大山町", "南部町", "伯耆町", "日南町", "日野町", "江府町"],
        "島根県": ["松江市", "浜田市", "出雲市", "益田市", "大田市", "安来市", "江津市", "雲南市", "奥出雲町", "飯南町", "川本町", "美郷町", "邑南町", "津和野町", "吉賀町", "海士町", "西ノ島町", "知夫村", "隠岐の島町"],
        "岡山県": ["岡山市", "倉敷市", "津山市", "玉野市", "笠岡市", "井原市", "総社市", "高梁市", "新見市", "備前市", "瀬戸内市", "赤磐市", "真庭市", "美作市", "浅口市", "和気町", "早島町", "里庄町", "矢掛町", "新庄村", "鏡野町", "勝央町", "奈義町", "西粟倉村", "久米南町", "美咲町", "吉備中央町"],
        "広島県": ["広島市", "呉市", "竹原市", "三原市", "尾道市", "福山市", "三次市", "庄原市", "大竹市", "東広島市", "廿日市市", "安芸高田市", "江田島市", "府中町", "海田町", "熊野町", "坂町", "安芸太田町", "北広島町", "大崎上島町", "世羅町", "神石高原町"],
        "山口県": ["下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市", "光市", "長門市", "柳井市", "美祢市", "周南市", "山陽小野田市", "周防大島町", "和木町", "上関町", "田布施町", "平生町", "阿武町"]
    },
    "四国": {
        "徳島県": ["徳島市", "鳴門市", "小松島市", "阿南市", "吉野川市", "阿波市", "美馬市", "三好市", "勝浦町", "上勝町", "佐那河内村", "石井町", "神山町", "那賀町", "牟岐町", "美波町", "海陽町", "松茂町", "北島町", "藍住町", "板野町", "上板町", "つるぎ町", "東みよし町"],
        "香川県": ["高松市", "丸亀市", "坂出市", "善通寺市", "観音寺市", "さぬき市", "東かがわ市", "三豊市", "土庄町", "小豆島町", "三木町", "直島町", "宇多津町", "綾川町", "琴平町", "多度津町", "まんのう町"],
        "愛媛県": ["松山市", "今治市", "宇和島市", "八幡浜市", "新居浜市", "西条市", "大洲市", "伊予市", "四国中央市", "西予市", "東温市", "上島町", "久万高原町", "松前町", "砥部町", "内子町", "伊方町", "鬼北町", "松野町", "愛南町"],
        "高知県": ["高知市", "室戸市", "安芸市", "南国市", "土佐市", "須崎市", "宿毛市", "土佐清水市", "四万十市", "香南市", "香美市", "東洋町", "奈半利町", "田野町", "安田町", "北川村", "馬路村", "芸西村", "本山町", "大豊町", "土佐町", "大川村", "いの町", "仁淀川町", "中土佐町", "佐川町", "越知町", "檮原町", "日高村", "津野町", "四万十町", "大月町", "三原村", "黒潮町"]
    },
    "九州": {
        "福岡県": ["福岡市", "北九州市", "大牟田市", "久留米市", "直方市", "飯塚市", "田川市", "柳川市", "八女市", "筑後市", "大川市", "行橋市", "豊前市", "中間市", "小郡市", "筑紫野市", "春日市", "大野城市", "宗像市", "太宰府市", "古賀市", "福津市", "うきは市", "宮若市", "嘉麻市", "朝倉市", "みやま市", "糸島市", "那珂川市", "宇美町", "篠栗町", "志免町", "須恵町", "新宮町", "久山町", "粕屋町", "芦屋町", "水巻町", "岡垣町", "遠賀町", "小竹町", "鞍手町", "桂川町", "筑前町", "東峰村", "大刀洗町", "大木町", "広川町", "香春町", "添田町", "糸田町", "川崎町", "大任町", "赤村", "福智町", "苅田町", "みやこ町", "吉富町", "上毛町", "築上町"],
        "佐賀県": ["佐賀市", "唐津市", "鳥栖市", "多久市", "伊万里市", "武雄市", "鹿島市", "小城市", "嬉野市", "神埼市", "吉野ヶ里町", "基山町", "上峰町", "みやき町", "玄海町", "有田町", "大町町", "江北町", "白石町", "太良町"],
        "長崎県": ["長崎市", "佐世保市", "島原市", "諫早市", "大村市", "平戸市", "松浦市", "対馬市", "壱岐市", "五島市", "西海市", "雲仙市", "南島原市", "長与町", "時津町", "東彼杵町", "川棚町", "波佐見町", "小値賀町", "佐々町", "新上五島町"],
        "熊本県": ["熊本市", "八代市", "人吉市", "荒尾市", "水俣市", "玉名市", "山鹿市", "菊池市", "宇土市", "上天草市", "宇城市", "阿蘇市", "天草市", "合志市", "美里町", "玉東町", "南関町", "長洲町", "和水町", "大津町", "菊陽町", "南小国町", "小国町", "産山村", "高森町", "西原村", "南阿蘇村", "御船町", "嘉島町", "益城町", "甲佐町", "山都町", "氷川町", "芦北町", "津奈木町", "錦町", "多良木町", "湯前町", "水上村", "相良村", "五木村", "山江村", "球磨村", "あさぎり町", "苓北町"],
        "大分県": ["大分市", "別府市", "中津市", "日田市", "佐伯市", "臼杵市", "津久見市", "竹田市", "豊後高田市", "杵築市", "宇佐市", "豊後大野市", "由布市", "国東市", "姫島村", "日出町", "九重町", "玖珠町"],
        "宮崎県": ["宮崎市", "都城市", "延岡市", "日南市", "小林市", "日向市", "串間市", "西都市", "えびの市", "三股町", "高原町", "国富町", "綾町", "高鍋町", "新富町", "西米良村", "木城町", "川南町", "都農町", "門川町", "諸塚村", "椎葉村", "美郷町", "高千穂町", "日之影町", "五ヶ瀬町"],
        "鹿児島県": ["鹿児島市", "鹿屋市", "枕崎市", "阿久根市", "出水市", "指宿市", "西之表市", "垂水市", "薩摩川内市", "日置市", "曽於市", "霧島市", "いちき串木野市", "南さつま市", "志布志市", "奄美市", "南九州市", "伊佐市", "姶良市", "三島村", "十島村", "さつま町", "長島町", "湧水町", "大崎町", "東串良町", "錦江町", "南大隅町", "肝付町", "中種子町", "南種子町", "屋久島町", "大和村", "宇検村", "瀬戸内町", "龍郷町", "喜界町", "徳之島町", "天城町", "伊仙町", "和泊町", "知名町", "与論町"]
    }
}



def allowed_file(filename):
    """Check if the file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _fill_student_data_from_form(student, form):
    """Helper to map form fields to student object."""
    student.name_kana = form.get("student_name_kana") or form.get("name_kana")
    student.country_of_origin = form.get("country_of_origin")
    student.native_language = form.get("native_language")
    student.other_languages = form.get("other_languages")
    student.occupation = form.get("occupation")
    student.residential_area = form.get("residential_area")
    student.jlpt_level = form.get("jlpt_level")
    student.learning_purpose = form.get("learning_purpose")
    student.life_troubles = form.get("life_troubles")
    student.how_knew_class = form.get("how_knew_class")
    student.how_knew_class_other = form.get("how_knew_class_other")
    return student


def upload_face_photo_to_cloudinary(file):
    """
    顔写真をCloudinaryにアップロードし、URLを返します。
    エラーが発生した場合はNoneとエラーメッセージを返します。
    """
    if not file or file.filename == "":
        return None, "顔写真をアップロードしてください。"
    if not allowed_file(file.filename):
        return None, "許可されていないファイル形式です。"

    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder="students",
            eager=[
                {"crop": "thumb", "gravity": "face", "zoom": 0.7,
                 "width": 200, "height": 200, "fetch_format": "auto", "quality": "auto"}
            ]
        )
        # eager変換が成功した場合のURLを取得
        if upload_result and 'eager' in upload_result and len(upload_result['eager']) > 0:
            return upload_result['eager'][0].get('secure_url'), None
        return None, "Cloudinaryへのアップロードは成功しましたが、変換されたURLが見つかりません。"
    except Exception as e:
        current_app.logger.error(f"Cloudinary upload failed: {e}")
        return None, f"画像アップロード中にエラーが発生しました: {str(e)}"


@student_bp.route("/create", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create_student():
    """Register a new student and create an initial learning record."""
    if request.method == "POST":
        # --- 1. 画像ファイルの保存処理 ---
        file = request.files.get("face_photo")
        face_photo_path, error_message = upload_face_photo_to_cloudinary(file)
        
        if error_message:
            flash(error_message, "danger")
            return render_template("student/create.html", staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))

        try:
            new_student = Student(face_photo_path=face_photo_path)
            _fill_student_data_from_form(new_student, request.form)
            
            db.session.add(new_student)
            db.session.flush()  # new_student.id を確定させる

            today_content = request.form.get("today_learning_content")
            if today_content:
                # Find the Staff record associated with the User
                staff_record = Staff.query.filter_by(user_id=current_user.id).first()
                if staff_record:
                    new_record = LearningRecord(
                        student_id=new_student.id,
                        staff_id=staff_record.id,
                        today_learning_content=today_content,
                        lesson_date=date.today()
                    )
                    db.session.add(new_record)

            db.session.commit()
            flash("受講生の新規登録と学習記録の保存が完了しました！", "success")
            return redirect(url_for("student.student_list"))

        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {str(e)}", "danger")
    staff_list = Staff.query.all()

    return render_template("student/create.html", staff_list=staff_list, region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))


@student_bp.route("/")
@login_required
def student_list():
    """Display the list of active and inactive students."""
    # Calculate threshold for inactive students (60 days)
    threshold_date = (datetime.now(timezone.utc) - timedelta(days=60)).date()
    
    active_students = []     # 2ヶ月以内に学習録がある生徒
    inactive_students = []   # 最後の学習録から2ヶ月以上経っている生徒
    
    # N+1問題を解決するために、各受講生の最新の学習日をサブクエリで一括取得
    latest_record_sub = db.session.query(
        LearningRecord.student_id,
        db.func.max(LearningRecord.lesson_date).label("latest_date")
    ).group_by(LearningRecord.student_id).subquery()

    students_with_date = db.session.query(Student, latest_record_sub.c.latest_date)\
        .outerjoin(latest_record_sub, Student.id == latest_record_sub.c.student_id)\
        .all()
    
    for student, latest_date in students_with_date:
        student.display_image = student.face_photo_path
        student.latest_log_date = latest_date
        
        if latest_date:
            if latest_date < threshold_date:
                inactive_students.append(student)
            else:
                active_students.append(student)
        else:
            inactive_students.append(student)
            
    return render_template(
        'student/list.html', 
        active_students=active_students, 
        inactive_students=inactive_students
    )


# app/student/routes.py 内
@student_bp.route("/<int:id>/update", methods=["GET", "POST"])
def update_student(id):
    """Update existing student information."""
    student = Student.query.get_or_404(id)

    if request.method == "POST":
        _fill_student_data_from_form(student, request.form)

        file = request.files.get("face_photo")
        if file and file.filename:
            face_photo_path, error_message = upload_face_photo_to_cloudinary(file)
            if error_message:
                flash(error_message, "danger")
                return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))
            if face_photo_path:
                student.face_photo_path = face_photo_path

        try:
            db.session.commit()
            flash(f"{student.name_kana} さんの情報を更新しました。", "success")
            return redirect(url_for("student.student_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")
    return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))


@student_bp.route('/attendance')
@login_required
def attendance_list():
    # 1. クエリパラメータから日付を取得（指定がなければ今日の日付）
    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = datetime.now().date()

    # 2. その日の学習録（出席データ）をすべて取得
    # student や staff のリレーションをまとめて読み込む(joinedload)と処理が高速になります
    logs = LearningRecord.query.filter_by(lesson_date=target_date).all()

    # 3. 国籍ごとに生徒をグループ化する辞書を作成
    # 構造: { "ベトナム": [生徒1, 生徒2], "ミャンマー": [生徒3] }
    grouped_students = defaultdict(list)
    
    for log in logs:
        student = log.student
        if student:
            # テンプレート側で表示しやすいように、担当スタッフの名前を一時的に生徒オブジェクトに持たせる
            # print(dir(log.staff_id))
            staff_info = User.query.filter_by(id=log.staff_id).first().name
            student.assigned_staff_name =  staff_info if staff_info else "自習"
            # 国籍をキーにしてグループに追加
            country = student.country_of_origin or "不明"
            grouped_students[country].append(student)

    return render_template(
        'student/attendence.html',
        target_date=target_date,
        grouped_students=dict(grouped_students), # 扱いやすいように通常の辞書型に変換
        total_count=len(logs)
    )
    

# PDF生成用の定数
PDF_HEADER_ROW_HEIGHT = 10
PDF_DATA_ROW_HEIGHT = 20
PDF_COL_WIDTH_NO = 15
PDF_COL_WIDTH_NAME = 60
PDF_COL_WIDTH_PHOTO = 20
PDF_COL_WIDTH_COUNTRY = 30
PDF_COL_WIDTH_STAFF = 30
PDF_COL_WIDTH_NEXT_DATE = 30
PDF_ROWS_PER_PAGE = 12 # 1ページあたりのデータ行数
PDF_NEXT_DATE_OFFSET_DAYS = 8 # 次回日付の計算オフセット


# FPDFに日本語フォントを読み込ませるための準備
# 1. プロジェクト内に .ttf フォントファイルを用意してください（例: fonts/ipaexg.ttf）
# 2. Vercelの制限を回避するため、外部コンパイルが不要なこの構成で動かします

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", 'B', 12)
        self.cell(0, 10, 'Attendance List', 0, 1, 'C')

def get_pdf_image(image_path_or_url):
    if not image_path_or_url: return ""
    if image_path_or_url.startswith(('http://', 'https://')):
        try:
            response = requests.get(image_path_or_url, timeout=5)
            if response.status_code == 200:
                base64_data = base64.b64encode(response.content).decode('utf-8')
                mime_type = "image/png" if "png" in image_path_or_url.lower() else "image/jpeg"
                return f"data:{mime_type};base64,{base64_data}"
        except Exception: pass
    return ""

@student_bp.route('/attendance/download-pdf')
@login_required
def download_attendance_pdf():
    date_str = request.args.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
    
    logs = LearningRecord.query.filter_by(lesson_date=target_date).all()
    
    # PDF生成
    pdf = PDF()
    pdf.add_page()
    
    # 簡易テーブル作成（FPDFのCellを使用）
    font_path = os.path.join(current_app.root_path, 'fonts', 'ipaexg.ttf')
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.set_font("IPAexGothic", size=10)

    next_date = datetime.strptime(date_str, '%Y-%m-%d').date() + timedelta(days=8) if date_str else datetime.now().date() + timedelta(days=8)
    # headers = ["No", "Name", "", "Country", "Staff", str(next_date)]
    pdf.cell(15, 10, "No", border=1)
    pdf.cell(60, 10, "Name", border=1)
    pdf.cell(20, 10, "Photo", border=1)
    pdf.cell(30, 10, "Country", border=1)
    pdf.cell(30, 10, "Staff", border=1)
    pdf.cell(30, 10, str(next_date), border=1)
    pdf.ln()
    
    count = 0
    for log in logs:
        if (count % 12 == 0 and count != 0):
            pdf.cell(15, 10, "No", border=1)
            pdf.cell(60, 10, "Name", border=1)
            pdf.cell(20, 10, "Photo", border=1)
            pdf.cell(30, 10, "Country", border=1)
            pdf.cell(30, 10, "Staff", border=1)
            pdf.cell(30, 10, str(next_date), border=1)
            pdf.ln()
        student = log.student
        if student:
            count += 1
            staff_name = User.query.get(log.staff_id).name if log.staff_id else "未定"
            
            # 画像データはVercelのメモリ制限を避けるため、今回は一旦テキスト情報のみで出力
            # FPDFに画像を追加する場合は pdf.image() を使いますが、URLからは直接読み込めないため
            # 必要であれば事前にキャッシュフォルダへ保存する等のロジックが必要です
            row_height = 20
            
            pdf.cell(15, row_height, str(count), border=1)
            pdf.cell(60, row_height, student.name_kana, border=1) # 文字数制限
            try:
                response = requests.get(student.face_photo_path, timeout=5)
                if response.status_code == 200:
                    # 2. メモリ上に画像を読み込む
                    image_data = io.BytesIO(response.content)
                    x_pos = pdf.get_x()
                    y_pos = pdf.get_y()
                    cell_width = 20
                    pdf.cell(cell_width, row_height, "", border=1)
        
                    # 3. PDFに画像を配置
                    # x, y は枠内の位置、wは画像幅
                    pdf.image(
                        image_data,
                        x=x_pos + 1, 
                        y=y_pos + 1, 
                        w=cell_width - 2, 
                        h=row_height - 2
                    )
                    # pdf.set_x(x_pos + cell_width)
                else:
                    print(f"画像取得失敗: ステータスコード {response.status_code}")
            except Exception as e:
                print(f"画像ダウンロードエラー: {e}")
            # pdf.image(student.face_photo_path, x=40 + 1, y=40 + 1, w=40 - 2, h=40 - 2)
            # pdf.cell(40, 40, get_pdf_image(student.face_photo_path), border=1)
            pdf.cell(30, row_height, student.country_of_origin or "N/A", border=1)
            pdf.cell(30, row_height, staff_name, border=1)
            pdf.cell(30, row_height, "", border=1)
            pdf.ln()

    # ストリームに出力
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_data = pdf_buffer.getvalue()
    
    # 応答を作成
    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=attendance_{target_date}.pdf'
    
    return response