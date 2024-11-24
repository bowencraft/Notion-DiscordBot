import requests
from bs4 import BeautifulSoup
from database import SessionLocal, engine
import models
import json
import validators
from functionality.security import *
import aiohttp
db = SessionLocal()


class SearchData:
    id = ""
    title = ""
    url = ""

    def __init__(self, id, title, url):
        self.id = id
        self.title = title
        self.url = url


def getTitle(url):
    try:
        request = requests.get(url)
        soup = BeautifulSoup(request.text, "html.parser")
        title_tag = soup.find("title")
        return title_tag.get_text()
    except:
        return None


def checkURL(url):
    if validators.url(url):
        return True
    return False


def getTags(args):
    url = args[0]
    # Tag provided
    final_tag = []
    list_of_tags = []

    # Multiple
    for tag in args[1:]:
        # Adding the arguments to list_of_tags
        list_of_tags.append(tag)
        for tag in list_of_tags:
            # Splitting the arguments to get the tags
            tag_list = tag.split(",")
            for single_tag in tag_list:
                if single_tag.strip() == "":
                    pass
                # Appending tag to the final_tag dict
                print(single_tag.strip().lower())
                if {"name": single_tag.strip().lower()} not in final_tag:
                    final_tag.append({"name": single_tag.strip().lower()})
                else:
                    pass
    if len(final_tag) > 0:
        return final_tag
    else:
        return [{"name": "misc"}]


def getSearchTagsPayload(tags):
    final_tag = []
    list_of_tags = []

    # Multiple
    for tag in tags:
        # Adding the arguments to list_of_tags
        list_of_tags.append(tag)

        for tag in list_of_tags:
            # Splitting the arguments to get the tags
            tag_list = tag.split(",")
            for single_tag in tag_list:
                if single_tag.strip() == "":
                    continue
                # Appending tag to the final_tag dict
                final_tag.append(
                    {
                        "property": "Tag",
                        "multi_select": {"contains": single_tag.strip().lower()},
                    }
                )
    return final_tag

def getResults(url, payload, headers):
    response = requests.post(url, headers=headers, data=payload)
    results = response.json()
    return results

def searchTag(notion_db_id, notion_api_key, tags):
    # Search for a tag
    url = "https://api.notion.com/v1/databases/" + notion_db_id + "/query"
    payload = json.dumps({"filter": {"and": tags}})
    headers = {
        "Authorization": notion_api_key,
        "Notion-Version": "2021-05-13",
        "Content-Type": "application/json",
    }

    data = getResults(url, payload, headers)
    query_results = data["results"]
    no_of_results = len(query_results)

    search_results = []
    if no_of_results == 0:
        # No results found
        return search_results
    for result in query_results:
        # Create Search Object for each result
        search_object = SearchData(
            id=result["id"],
            url=result["properties"]["URL"]["url"].strip(),
            title=result["properties"]["Title"]["rich_text"][0]["plain_text"].strip(),
        )
        search_results.append(search_object)
    
    while data["next_cursor"]:
        # pagination
        payload = json.dumps({"filter": {"and": tags}, "cursor": data["next_cursor"]})
        data = getResults(url, payload, headers)
        query_results = data["results"]
        no_of_results = len(query_results)
        if no_of_results == 0:
            return search_results
        for result in query_results:
            # Create Search Object for each result
            search_object = SearchData(
                id=result["id"],
                url=result["properties"]["URL"]["url"].strip(),
                title=result["properties"]["Title"]["rich_text"][0]["plain_text"].strip(),
            )
            search_results.append(search_object)
    return search_results


def getGuildData():
    data = {}
    guilds = db.query(models.Clients).all()
    for guild in guilds:
        data[str(guild.guild_id)] = guild
    return data


def getPrefixes():
    prefixes = {}
    guilds = db.query(models.Clients).all()
    for guild in guilds:
        prefixes[str(guild.guild_id)] = guild.prefix
    return prefixes


def checkIfGuildPresent(guildId):
    guild = db.query(models.Clients).filter(models.Clients.guild_id == guildId).first()
    if guild:
        return True
    return False


def getQueryForTitle(args):
    query = ""
    # check args
    if len(args) > 0:
        # received data
        for arg in args:
            query += arg + " "
    else:
        # no data received
        return None
    query = query.strip()
    return query


def deserialize(data):
    obj = models.Clients(
        data["guild_id"],
        data["notion_api_key"],
        data["notion_db_id"],
        data["tag"],
        data["prefix"],
    )
    return obj

def fixDatabase():
    # update database
    guilds = db.query(models.Clients).all()
    data = {}
    for guild in guilds:
        data[str(guild.guild_id)] = guild
        # encrypt api key and db key
        guild.notion_api_key = encrypt(guild.notion_api_key)
        guild.notion_db_id = encrypt(guild.notion_db_id)
        # update
        db.commit()
    return data


def getGuildInfo():
    # 读取guild_data.json
    guilds = db.query(models.Clients).all()
    # 检查是否加密
    data = {}
    for guild in guilds:
        if getKey(guild.notion_api_key):
            # 已加密
            obj = models.Clients(
                guild.guild_id,
                getKey(guild.notion_api_key),
                guild.prefix
            )
            data[str(guild.guild_id)] = obj
        else:
            # 数据库需要加密
            print("Database not encrypted! Start encryption")
            print("Database fixed")
            fixDatabase()
            return getGuildInfo()
            
    print(data)
    return data

def doesItExist(link, api_key, db_id):
    url = "https://api.notion.com/v1/databases/" + db_id + "/query"
    payload = json.dumps({"filter": {"property": "URL", "url": {"equals": link}}})
    headers = {
        "Authorization": api_key,
        "Notion-Version": "2021-05-13",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, data=payload)
    try:
        result = response.json()["results"]
    except:
        return False
    if len(result) == 0:
        return False
    return True


def getFileTags(args):
    # Tag provided
    final_tag = []
    list_of_tags = []

    # Multiple
    for tag in args:
        # Adding the arguments to list_of_tags
        list_of_tags.append(tag)

        for tag in list_of_tags:
            # Splitting the arguments to get the tags
            tag_list = tag.split(",")
            for single_tag in tag_list:
                if single_tag.strip() == "":
                    continue
                # Appending tag to the final_tag dict
                final_tag.append({"name": single_tag.strip().lower()})
    if len(final_tag) > 0:
        return final_tag
    else:
        return [{"name": "misc"}]

def queryNotion(notion_api_key, database_id, query_data):
    """
    查询 Notion 数据库
    """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        'Authorization': notion_api_key,
        'Notion-Version': '2021-08-16',
        'Content-Type': 'application/json'
    }
    
    try:
        print(f"正在查询Notion数据库: {database_id}")
        print(f"查询条件: {json.dumps(query_data, indent=2)}")
        
        payload = json.dumps(query_data)
        response = requests.post(url, headers=headers, data=payload)
        
        print(f"Notion API响应状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"找到 {len(result.get('results', []))} 条更新")
            return result
        else:
            print(f"Notion API错误响应: {response.text}")
            return {"results": []}
    except Exception as e:
        print(f"查询 Notion 时出错: {e}")
        return {"results": []}
