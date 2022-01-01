import requests
from bs4 import BeautifulSoup
from database import SessionLocal, engine
import models
import json
import validators

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


def searchTag(notion_db_id, notion_api_key, tags):
    # Search for a tag
    url = "https://api.notion.com/v1/databases/" + notion_db_id + "/query"
    payload = json.dumps({"filter": {"and": tags}})
    headers = {
        "Authorization": notion_api_key,
        "Notion-Version": "2021-05-13",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, data=payload)

    query_results = response.json()["results"]
    no_of_results = len(query_results)

    search_results = []
    if no_of_results == 0:
        # No results found
        return search_results
    for result in query_results:
        # Create Search Object for each result
        search_object = SearchData(
            id=result["id"],
            url=result["properties"]["URL"]["url"],
            title=result["properties"]["Title"]["rich_text"][0]["plain_text"],
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


# testing purposes only
# for obj in searchByTitle("django", "9e449365893e4657a5502f4723771ece", "secret_D50ybSSLDed6mTFOy188nHShw2XWPh2v1FFiUAviMfG"):
#  print(obj.title)


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
        data["contributor"],
        data["prefix"],
    )
    return obj


def getGuildInfo():
    # read guild_data.json
    with open("guild_data.json", "r") as f:
        data = json.load(f)
    print(data)

    obj_dict = {}
    for guild in data:
        obj_dict[guild] = deserialize(data[guild])
    return obj_dict


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
