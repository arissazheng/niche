import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sourcing.api import create_app
from sourcing.config import Settings
from sourcing.models import SearchRequest
from sourcing.pipeline import Pipeline, eligible
from sourcing.sources import FixtureSources, normalize, ApifySources
from sourcing.store import Store

@pytest.fixture
def request_data():
    return SearchRequest.model_validate_json(Path('examples/search.json').read_text())

@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path/'test.sqlite'))


def test_pipeline_end_to_end(request_data, store):
    ident = store.create(request_data.model_dump())
    asyncio.run(Pipeline(Settings(),store).run(request_data,ident))
    result = store.get(ident)
    assert result['status']=='completed'
    assert len(result['sources'])==4
    assert len(result['results'])==12
    assert all(x['is_fixture'] and x['price']<=80 and x['available'] for x in result['results'])
    assert all('Shipping destination unverified' in x['warnings'] for x in result['results'])


def test_filters_unknown_and_sold(request_data):
    items,_ = asyncio.run(FixtureSources().fetch('etsy','',50,''))
    request_data.request.unknown_policy='exclude'
    assert not eligible(items,request_data)
    request_data.request.unknown_policy='include_with_warning'
    items[0].currency='EUR'
    items[1].sizes=['12']
    filtered = eligible(items,request_data)
    assert {x.id for x in filtered}=={'etsy:fixture-2','etsy:fixture-3'}


def test_no_used_when_new_required(request_data):
    items,_ = asyncio.run(FixtureSources().fetch('etsy','',50,''))
    request_data.request.allow_secondhand=False
    assert eligible(items,request_data)==[]


def test_normalization_does_not_invent_currency_or_stock():
    row = {'id':1,'title':'Trousers','url':'https://www.etsy.com/listing/1?tracking=x','price':25,'currency':'USD','available':'false'}
    item = normalize('etsy',row,{})
    assert item.available is None
    assert item.url=='https://www.etsy.com/listing/1'
    assert item.seller_type=='unknown'
    assert normalize('etsy',{**row,'currency':None},{}) is None
    assert normalize('etsy',{**row,'url':'https://evil.test/listing/1'},{}) is None
    assert normalize('etsy',{**row,'price':float('nan')},{}) is None


def test_partial_source_failure(request_data,store):
    class Sources(FixtureSources):
        async def fetch(self,source,*args):
            if source=='etsy':
                raise TimeoutError()
            return await super().fetch(source,*args)
    ident = store.create(request_data.model_dump())
    asyncio.run(Pipeline(Settings(),store,sources=Sources()).run(request_data,ident))
    result = store.get(ident)
    assert result['status']=='partial'
    assert result['sources']['etsy']['status']=='failed'
    assert result['results']


def test_all_source_failure(request_data,store):
    class Sources:
        async def fetch(self,*args):
            raise RuntimeError()
    ident = store.create(request_data.model_dump())
    asyncio.run(Pipeline(Settings(),store,sources=Sources()).run(request_data,ident))
    assert store.get(ident)['status']=='failed'


def test_restart_does_not_repeat_chargeable_job(request_data,store):
    ident = store.create(request_data.model_dump())
    store.update(ident,'running',{})
    store.recover()
    assert store.get(ident)['status']=='interrupted'
    assert not store.pending()


def test_api_auth_validation_feedback(tmp_path,request_data):
    import time
    app = create_app(Settings(database_path=str(tmp_path/'api.sqlite'),sourcing_api_key='test'))
    headers={'X-API-Key':'test'}
    with TestClient(app) as client:
        assert client.post('/v1/searches',json=request_data.model_dump()).status_code==401
        assert client.post('/v1/searches',headers=headers,json={}).status_code==422
        response=client.post('/v1/searches',headers=headers,json=request_data.model_dump())
        assert response.status_code==202
        url=response.json()['status_url']
        for _ in range(40):
            result=client.get(url,headers=headers).json()
            if result['status']=='completed':
                break
            time.sleep(.05)
        assert result['status']=='completed'
        assert client.post(url+'/feedback',headers=headers,json={'listing_id':'fake','liked':True}).status_code==422
        assert client.post(url+'/feedback',headers=headers,json={'listing_id':result['results'][0]['id'],'liked':True}).status_code==201


def test_live_requires_credentials():
    with pytest.raises(ValueError):
        Settings(sourcing_mode='live',apify_token='',anthropic_api_key='').validate_live()


def test_adapter_run_caps(store):
    sources=ApifySources(Settings(),store)
    _,payload=sources.actor_input('depop','linen trousers',30)
    assert payload['maxItems']==30
    assert payload['includeSellerListings'] is False


def test_claude_rejects_hallucinated_id(request_data,store):
    from sourcing.claude import Claude
    class BadModel(Claude):
        async def call(self,*args,**kwargs):
            return {'rankings':[{'id':'made-up','score':100}]}
    items,_=asyncio.run(FixtureSources().fetch('etsy','',1,''))
    # Invented ids are skipped, never turned into listings; with nothing valid left the ranking fails.
    with pytest.raises(ValueError,match='Missing'):
        asyncio.run(BadModel(Settings(),store).rank(request_data,items,'job'))


def test_claude_ranker_sends_photos_inline(monkeypatch,request_data,store):
    import httpx
    from sourcing.claude import Claude
    original=httpx.AsyncClient
    import io
    from PIL import Image
    buffer=io.BytesIO(); Image.new('RGB',(1200,900),(20,20,20)).save(buffer,format='JPEG'); jpeg=buffer.getvalue()
    def handler(request):
        if 'gstatic' in request.url.host:
            return httpx.Response(200,content=jpeg,headers={'content-type':'text/html'})
        return httpx.Response(404)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    from sourcing import safe_fetch
    async def public_dns(host):
        return ['93.184.216.34']
    monkeypatch.setattr(safe_fetch,'resolve',public_dns)  # keep the test offline
    sent=[]
    class Model(Claude):
        async def call(self,system,content,*args,**kwargs):
            sent.extend(content)
            return {'rankings':[{'id':f'L{i+1}','score':50,'dimensions':{'color':50,'silhouette':50,'aesthetic':50},
                'reason':'ok','uncertainties':[]} for i in range(len(items))]}
    items,_=asyncio.run(FixtureSources().fetch('etsy','',2,''))
    items[0].image_urls=['https://encrypted-tbn0.gstatic.com/shopping?q=tbn:abc']
    items[1].image_urls=['https://i.etsystatic.com/missing.jpg']
    asyncio.run(Model(Settings(),store).rank(request_data,items,'job'))
    images=[x for x in sent if x['type']=='image']
    assert len(images)==1 and images[0]['source']['type']=='base64' and images[0]['source']['media_type']=='image/jpeg'
    import base64
    shrunk=Image.open(io.BytesIO(base64.b64decode(images[0]['source']['data'])))
    assert max(shrunk.size)==512


def test_apify_http_contract_and_cache(monkeypatch,store):
    import httpx
    original=httpx.AsyncClient
    calls=[]
    def handler(request):
        calls.append(request)
        if request.method=='POST':
            assert request.url.params['maxTotalChargeUsd']=='0.5'
            assert json.loads(request.content)['maxItems']==30
            return httpx.Response(201,json={'data':{'id':'run1','status':'SUCCEEDED','defaultDatasetId':'ds1'}})
        return httpx.Response(200,json=[{'id':'1','title':'Trousers','url':'https://www.depop.com/products/1',
            'price':40,'currency':'USD','available':True}])
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    sources=ApifySources(Settings(apify_token='test'),store)
    items,status=asyncio.run(sources.fetch('depop','trousers',30,'job'))
    assert items[0].provenance['dataset_id']=='ds1'
    _,status=asyncio.run(sources.fetch('depop','trousers',30,'job'))
    assert status['status']=='cached'
    assert len(calls)==2


def test_claude_http_contract(store):
    import anthropic
    import httpx2
    from sourcing.claude import Claude,PLANNER
    def handler(request):
        payload=json.loads(request.content)
        assert payload['output_config']['format']['type']=='json_schema'
        assert payload['fallbacks']=='default'
        assert 'server-side-fallback-2026-07-01' in request.headers['anthropic-beta']
        assert request.headers['authorization']=='Bearer test'
        return httpx2.Response(200,json={'id':'msg_1','type':'message','role':'assistant','model':payload['model'],
            'stop_reason':'end_turn','content':[{'type':'text','text':'{"queries":["olive linen trousers"]}'}],
            'usage':{'input_tokens':100,'output_tokens':10}})
    client=anthropic.AsyncAnthropic(api_key='test',http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    result=asyncio.run(Claude(Settings(anthropic_api_key='test'),store,client=client).call(PLANNER,'test','job','planner',500))
    assert result['queries']==['olive linen trousers']


def test_grailed_documented_shape_and_inputs(store):
    row={'listing_id':'1','listing_url':'https://www.grailed.com/listings/1','title':'Jacket',
         'price':'40.00','currency':'USD','seller_username':'archive','image_url':'https://media.grailed.com/1.jpg'}
    item=normalize('grailed',row,{})
    assert item.id=='grailed:1' and item.seller=='archive'
    _,payload=ApifySources(Settings(),store).actor_input('grailed','jacket',30)
    assert payload=={'queries':['jacket'],'maxPagesPerQuery':1}


def niche_request(request_data, sources=('mainstream', 'secondhand')):
    data = request_data.model_dump(mode='json')
    data['sources'] = list(sources)
    data['taste_profile']['preferred_brands'] = ['Madewell']
    return SearchRequest.model_validate(data)


def test_niche_actors_feed_one_labelled_list(request_data, store):
    request = niche_request(request_data)
    ident = store.create(request.model_dump(mode='json'))
    asyncio.run(Pipeline(Settings(), store).run(request, ident))
    result = store.get(ident)
    assert result['status'] == 'completed' and set(result['sources']) == {'mainstream', 'secondhand'}
    assert {(x['retailer'], x['tier']) for x in result['results']} == {('Madewell', 'mainstream'), ('Depop', 'resale')}
    # Preferred brand gets the lexical bonus on the fallback ranking.
    by_title = {}
    for x in result['results']:
        by_title.setdefault(x['title'], {})[x['retailer']] = x['score']
    assert all(s['Madewell'] == s['Depop'] + 10 for s in by_title.values() if len(s) == 2)


def test_new_only_requests_skip_secondhand_actor(request_data, store):
    request = niche_request(request_data)
    request.request.allow_secondhand = False
    ident = store.create(request.model_dump(mode='json'))
    asyncio.run(Pipeline(Settings(), store).run(request, ident))
    assert set(store.get(ident)['sources']) == {'mainstream'}


def test_niche_actor_input_and_normalization(store):
    sources = ApifySources(Settings(), store)
    actor, payload = sources.actor_input('mainstream', ['wool coat', 'camel coat'], 30, 150.0)
    assert actor == 'zaarahemd/niche-mainstream'
    # Mainstream is capped for cost: one phrase, 10 results by default.
    assert payload == {'queries': ['wool coat'], 'itemsPerQuery': 10, 'maxPrice': 150}
    actor, payload = sources.actor_input('secondhand', ['wool coat', 'camel coat'], 30, None)
    assert actor == 'zaarahemd/niche-secondhand' and payload == {'queries': ['wool coat', 'camel coat'], 'itemsPerQuery': 15}
    row = {'id': 'vinted:7', 'marketplace': 'vinted', 'retailer': 'Vinted', 'tier': 'resale', 'title': 'Wool coat',
           'url': 'https://www.vinted.com/items/7', 'price': 20.0, 'currency': 'usd', 'image_urls': ['http://insecure/1.jpg'],
           'sizes': ['M'], 'condition': 'Very good', 'brand': 'Ralph Lauren', 'seller': 's', 'available': True,
           'is_ad': False, 'shipping_cost': None, 'description': ''}
    item = normalize('secondhand', row, {'run_id': 'r'})
    assert item.id == 'vinted:7' and item.source == 'secondhand' and item.retailer == 'Vinted' and item.currency == 'USD'
    assert item.image_urls == []  # non-https images are dropped
    assert normalize('secondhand', {**row, 'url': 'javascript:alert(1)'}, {}) is None


def test_claude_key_and_base_url_from_niche_env(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'reserved-by-host')
    monkeypatch.setenv('NICHE_ANTHROPIC_API_KEY', 'app-key')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://host-gateway.invalid')
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key == 'app-key'
    assert settings.anthropic_base_url == 'https://api.anthropic.com'
    monkeypatch.delenv('NICHE_ANTHROPIC_API_KEY')
    assert Settings(_env_file=None).anthropic_api_key == 'reserved-by-host'


def test_claude_partial_ranking_keeps_ranked_items(request_data,store):
    from sourcing.claude import Claude
    items,_=asyncio.run(FixtureSources().fetch('etsy','',3,''))
    class PartialModel(Claude):
        async def call(self,*args,**kwargs):
            return {'rankings':[{'id':'L1','score':91,'dimensions':{'color':90,'silhouette':90,'aesthetic':90},
                                 'reason':'Strong match','uncertainties':['Synthetic demo item; not for purchase','Fit unclear']}]}
    ranked=asyncio.run(PartialModel(Settings(),store).rank(request_data,items,'job'))
    assert ranked[0].score==91 and ranked[0].reason=='Strong match'
    assert ranked[0].warnings.count('Synthetic demo item; not for purchase')==1 and 'Fit unclear' in ranked[0].warnings
    assert all(x.score==0 and 'Taste match not evaluated' in x.warnings for x in ranked[1:])
    class EmptyModel(Claude):
        async def call(self,*args,**kwargs):
            return {'rankings':[]}
    with pytest.raises(ValueError,match='Missing'):
        asyncio.run(EmptyModel(Settings(),store).rank(request_data,items,'job'))


def test_shein_never_eligible(request_data):
    from sourcing.pipeline import excluded
    items,_=asyncio.run(FixtureSources().fetch('etsy','',4,''))
    items[0].retailer='Shein'
    items[1].title="DAZY Women's Bowknot Pleated Mini Skirt"
    items[2].url='https://us.shein.com/p/123.html'
    items[3].brand='SHEIN'
    assert all(excluded(x) for x in items)
    assert not eligible(items,request_data)
    clean,_=asyncio.run(FixtureSources().fetch('etsy','',1,''))
    clean[0].title='Sheinberg vintage wool skirt'  # word boundary: not a match
    assert not excluded(clean[0])


def test_fast_source_is_ranked_while_slow_source_still_fetching(request_data,store):
    import time
    events=[]
    class Sources(FixtureSources):
        async def fetch(self,source,*args,**kwargs):
            if source=='depop':
                await asyncio.sleep(0.3)
                events.append(('fetched',source,time.monotonic()))
            return await super().fetch(source,*args)
    class Model:
        async def plan(self,request,job_id):
            return ['skirt']
        async def rank(self,request,listings,job_id):
            events.append(('rank',listings[0].source,time.monotonic()))
            for x in listings:
                x.score,x.reason=50,'ok'
            return listings
    request_data.sources=['etsy','depop']
    settings=Settings(sourcing_mode='live',apify_token='t',anthropic_api_key='k')
    ident=store.create(request_data.model_dump())
    asyncio.run(Pipeline(settings,store,sources=Sources(),model=Model()).run(request_data,ident))
    rank_etsy=next(t for kind,src,t in events if kind=='rank' and src=='etsy')
    depop_done=next(t for kind,src,t in events if kind=='fetched')
    assert rank_etsy < depop_done
    assert store.get(ident)['ranking_method']=='claude'


def test_streamed_batches_are_ranked_as_they_arrive(request_data, store):
    # The secondhand actor pushes each marketplace as it finishes; the first batch is ranked before the second lands.
    request = niche_request(request_data, sources=('secondhand',))
    order = []

    class Streaming:
        async def stream(self, source, query, limit, job_id, max_price=None):
            items, _ = await FixtureSources().fetch(source, query, limit, job_id)
            yield items[:2], {'status': 'running'}
            await asyncio.sleep(0.05)
            order.append('second batch')
            yield items[2:4], {'status': 'running'}
            yield [], {'status': 'succeeded'}

    class Model:
        async def rank(self, request, batch, job_id):
            order.append(f'ranked {len(batch)}')
            for x in batch:
                x.score, x.match_dimensions, x.reason = 50, {}, 'ok'
            return batch

    settings = Settings(sourcing_mode='live', apify_token='t', anthropic_api_key='k')
    ident = store.create(request.model_dump(mode='json'))
    pipeline = Pipeline(settings, store, sources=Streaming(), model=Model())
    async def plan(*args):
        return ['trousers']
    pipeline.model.plan = plan
    result = asyncio.run(pipeline.run(request, ident))
    assert order[0] == 'ranked 2' and order[1] == 'second batch'
    assert result['sources']['secondhand']['status'] == 'succeeded' and result['ranking_method'] == 'claude'


def test_prefetch_is_ranked_ahead_and_shown_first(request_data, store):
    from sourcing.prefetch import Prefetcher
    request = niche_request(request_data, sources=('secondhand',))
    request.profile_id = 'p1'

    class Model:
        def __init__(self):
            self.ranked = []

        async def plan(self, *args):
            return ['olive trousers']

        async def rank(self, request, batch, job_id):
            self.ranked.append([x.id for x in batch])
            for x in batch:
                x.score, x.match_dimensions, x.reason = 50, {}, 'ok'
            return batch

    class Slow:
        async def fetch(self, source, query, limit, job_id, max_price=None):
            return await FixtureSources().fetch(source, query, limit, job_id)

    settings = Settings(sourcing_mode='live', apify_token='t', anthropic_api_key='k')
    asyncio.run(Prefetcher(settings, store, sources=Slow(), model=Model()).warm(request))
    assert store.prefetched('p1') and all(x['score'] == 50 for x in store.prefetched('p1'))  # ranked ahead of time

    class Live:
        async def stream(self, source, query, limit, job_id, max_price=None):
            yield [], {'status': 'succeeded'}

    model = Model()
    request.request.query = 'linen trousers'  # only the trousers in the prefetch match
    ident = store.create(request.model_dump(mode='json'))
    result = asyncio.run(Pipeline(settings, store, sources=Live(), model=model).run(request, ident))
    # Shown with the scores from the warm-up: no Claude call needed at search time.
    assert result['prefetched'] > 0 and model.ranked == [] and result['ranking_method'] == 'claude'
    assert all('trousers' in x['title'].lower() for x in result['results'])


def test_results_keep_a_mix_of_new_and_secondhand(request_data):
    from sourcing.pipeline import diversify
    items, _ = asyncio.run(FixtureSources().fetch('secondhand', '', 6, ''))
    more, _ = asyncio.run(FixtureSources().fetch('mainstream', '', 6, ''))
    for i, x in enumerate(items):
        x.seller, x.score = f's{i}', 90 - i
    for i, x in enumerate(more):
        x.seller, x.score = f'm{i}', 70 - i  # good fits, but every secondhand item scores higher
    picked = diversify(items + more, 8)
    assert sum(x.source == 'mainstream' for x in picked) == 2  # a quarter of 8
    assert [x.score for x in picked] == sorted((x.score for x in picked), reverse=True)
    for x in more:
        x.score = 30  # poor fits don't get a guaranteed place
    assert all(x.source == 'secondhand' for x in diversify(items + more, 6))
