import json
import redis
from django.shortcuts import render
from django.views.generic.base import View
from search.models import ArticleType, ZhiLianJobType
from django.http import HttpResponse
from elasticsearch import Elasticsearch
from datetime import datetime

es_client = Elasticsearch(hosts=["127.0.0.1"])
redis_client = redis.StrictRedis()


class IndexView(View):
    def get(self, request):
        topn_search = redis_client.zrevrangebyscore("search_keywords_top", "+inf", "-inf", start=0, num=5)
        return render(request, "index.html", {
            "topn_search": topn_search
        })


# Create your views here.
class SearchSuggest(View):
    def get(self, request):
        key_words = request.GET.get('s', '')
        s_type = request.GET.get("s_type", "article")

        re_datas = []
        if key_words:
            if s_type == "job":
                s = ZhiLianJobType.search()
            elif s_type == "question":
                s = ArticleType.search()
            else:
                s = ArticleType.search()

            s = s.suggest('my_suggest', key_words, completion={
                "field": "suggest",
                "fuzzy": {
                    "fuzziness": 2
                },
                "size": 10
            })
            suggestions = s.execute_suggest()
            for match in suggestions.my_suggest[0].options:
                source = match._source
                re_datas.append(source["title"])
        return HttpResponse(json.dumps(re_datas), content_type="application/json")


class SearchView(View):
    def get(self, request):
        key_words = request.GET.get("q", "")
        s_type = request.GET.get("s_type", "article")

        redis_client.zincrby("search_keywords_top", key_words)

        topn_search = redis_client.zrevrangebyscore("search_keywords_top", "+inf", "-inf", start=0, num=5)
        jobbole_count = redis_client.get("jobbole_count")
        zhilian_job_count = redis_client.get("zhilain_job_count")

        page = request.GET.get("p", "1")
        try:
            page = int(page)
        except:
            page = 1

        if s_type == "job":
            es_index = "zhilian"
        elif s_type == "question":
            es_index = "jobbole"
        else:
            es_index = "jobbole"
        start_time = datetime.now()
        response = es_client.search(
            index=es_index,
            body={
                "query": {
                    "multi_match": {
                        "query": key_words,
                        "fields": ["tags", "title", "content"]
                    }
                },
                "from":  (page-1)*10,
                "size": 10,
                "highlight": {
                    "pre_tags": ['<span class="keyWord">'],
                    "post_tags": ['</span>'],
                    "fields": {
                        "title": {},
                        "content": {},
                    }
                }
            }
        )

        end_time = datetime.now()
        last_seconds = (end_time-start_time).total_seconds()
        total_nums = response["hits"]["total"]
        if (page % 10) > 0:
            page_nums = int(total_nums/10) + 1
        else:
            page_nums = int(total_nums/10)
        hit_list = []
        for hit in response["hits"]["hits"]:
            hit_dict = {}
            if "title" in hit["highlight"]:
                hit_dict["title"] = "".join(hit["highlight"]["title"])
            else:
                hit_dict["title"] = hit["_source"]["title"]
            if "content" in hit["highlight"]:
                hit_dict["content"] = "".join(hit["highlight"]["content"])[:500]
            else:
                hit_dict["content"] = hit["_source"]["content"][:500]

            # hit_dict["create_date"] = hit["_source"]["create_date"]
            hit_dict["url"] = hit["_source"]["url"]
            hit_dict["score"] = hit["_score"]

            hit_list.append(hit_dict)

        return render(request, "result.html", {"page": page,
                                               "all_hits": hit_list,
                                               "key_words": key_words,
                                               "total_nums": total_nums,
                                               "page_nums": page_nums,
                                               "last_seconds": last_seconds,
                                               "jobbole_count": jobbole_count,
                                               "zhilian_job_count": zhilian_job_count,
                                               "topn_search": topn_search
                                              })
