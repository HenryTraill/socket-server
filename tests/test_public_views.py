import json
from datetime import datetime

import pytest
from sqlalchemy import update

from tcsocket.app.models import NameOptions, sa_companies, sa_contractors

from .conftest import create_con_skills


async def test_index(cli):
    r = await cli.get('/')
    assert r.status == 200
    assert "You're looking at TutorCruncher socket's API" in await r.text()


async def test_index_head(cli):
    r = await cli.head('/')
    assert r.status == 200
    assert '' == await r.text()


async def test_list_contractors(cli, db_conn):
    v = await db_conn.execute(
        sa_companies
        .insert()
        .values(name='testing', public_key='thepublickey', private_key='theprivatekey')
        .returning(sa_companies.c.id)
    )
    r = await v.first()
    company_id = r.id
    await db_conn.execute(
        sa_contractors
        .insert()
        .values(id=1, company=company_id, first_name='Fred', last_name='Bloggs', last_updated=datetime.now())
    )
    headers = {
        'HOST': 'www.example.com',
    }
    r = await cli.get(cli.server.app.router['contractor-list'].url_for(company='thepublickey'), headers=headers)
    assert r.status == 200, await r.text()
    assert r.headers.get('Access-Control-Allow-Origin') == '*'
    obj = await r.json()
    assert [
        {
            'id': 1,
            'link': '1-fred-b',
            'name': 'Fred B',
            'photo': 'https://socket.tutorcruncher.com/media/thepublickey/1.thumb.jpg',
            'tag_line': None,
            'primary_description': None,
            'town': None,
            'country': None,
            'distance': None,
            'url': 'https://socket.tutorcruncher.com/thepublickey/contractors/1',
        }
    ] == obj


async def test_list_contractors_name(cli, db_conn, company):
    await db_conn.execute(
        sa_contractors
        .insert()
        .values(id=1, company=company.id, first_name='Fred', last_name='Bloggs', last_updated=datetime.now())
    )
    r = await cli.get(cli.server.app.router['contractor-list'].url_for(company='thepublickey'))
    assert r.status == 200, await r.text()
    assert (await r.json())[0]['link'] == '1-fred-b'
    assert (await r.json())[0]['name'] == 'Fred B'

    await db_conn.execute((
        update(sa_companies)
        .values({'name_display': NameOptions.first_name})
        .where(sa_companies.c.public_key == company.public_key)
    ))
    r = await cli.get(cli.server.app.router['contractor-list'].url_for(company='thepublickey'))
    assert r.status == 200, await r.text()
    assert (await r.json())[0]['link'] == '1-fred'
    assert (await r.json())[0]['name'] == 'Fred'

    await db_conn.execute((
        update(sa_companies)
        .values({'name_display': NameOptions.full_name})
        .where(sa_companies.c.public_key == company.public_key)
    ))
    r = await cli.get(cli.server.app.router['contractor-list'].url_for(company='thepublickey'))
    assert r.status == 200, await r.text()
    assert (await r.json())[0]['link'] == '1-fred-bloggs'
    assert (await r.json())[0]['name'] == 'Fred Bloggs'


@pytest.mark.parametrize('headers, newline_count', [
    ({'Accept': 'application/json'}, 0),
    ({'Accept': '*/*'}, 14),
    (None, 14),
])
async def test_json_encoding(cli, db_conn, company, headers, newline_count):
    await db_conn.execute(
        sa_contractors
        .insert()
        .values(id=1, company=company.id, first_name='Fred', last_name='Bloggs', last_updated=datetime.now())
    )
    r = await cli.get(cli.server.app.router['contractor-list'].url_for(company='thepublickey'), headers=headers)
    assert r.status == 200
    assert (await r.text()).count('\n') == newline_count


async def test_get_contractor(cli, db_conn):
    v = await db_conn.execute(
        sa_companies
        .insert()
        .values(name='testing', public_key='thepublickey', private_key='theprivatekey')
        .returning(sa_companies.c.id)
    )
    r = await v.first()
    company_id = r.id
    v = await db_conn.execute(
        sa_contractors
        .insert()
        .values(
            id=1,
            company=company_id,
            first_name='Fred',
            last_name='Bloggs',
            last_updated=datetime.now(),
            extra_attributes=[{'foo': 'bar'}]
        )
        .returning(sa_contractors.c.id)
    )
    con_id = (await v.first()).id
    await create_con_skills(db_conn, con_id)

    r = await cli.get(cli.server.app.router['contractor-get'].url_for(company='thepublickey', id=con_id, slug='x'))
    assert r.status == 200
    obj = await r.json()
    assert {
        'id': 1,
        'name': 'Fred B',
        'town': None,
        'country': None,
        'extra_attributes': [{'foo': 'bar'}],
        'tag_line': None,
        'photo': 'https://socket.tutorcruncher.com/media/thepublickey/1.jpg',
        'primary_description': None,
        'skills': [
            {
                'category': 'English',
                'qual_levels': ['A Level'],
                'subject': 'Language'
            },
            {
                'category': 'Maths',
                'qual_levels': ['GCSE'],
                'subject': 'Mathematics'
            }
        ],
    } == obj


async def test_missing_url(cli):
    r = await cli.get('/foobar')
    assert r.status == 404, await r.text()


async def test_get_enquiry(cli, company, other_server):
    r = await cli.get(cli.server.app.router['enquiry'].url_for(company=company.public_key))
    assert r.status == 200, await r.text()
    data = await r.json()
    assert len(data) == 3
    assert data['visible'][0]['field'] == 'client_name'
    assert data['visible'][0]['max_length'] == 255
    assert data['last_updated'] == 0
    # once to get immediate response, once "on the worker"
    assert other_server.app['request_log'] == ['enquiry_options', 'enquiry_options']

    r = await cli.get(cli.server.app.router['enquiry'].url_for(company=company.public_key))
    assert r.status == 200, await r.text()
    data = await r.json()
    assert len(data) == 3
    assert 1e9 < data['last_updated'] < 2e9
    # no more requests as data came from cache
    assert other_server.app['request_log'] == ['enquiry_options', 'enquiry_options']


async def test_post_enquiry(cli, company, other_server):
    data = {
        'client_name': 'Cat Flap',
        'client_phone': '123',
        'grecaptcha_response': 'good' * 5,
    }
    url = cli.server.app.router['enquiry'].url_for(company=company.public_key)
    r = await cli.post(url, data=json.dumps(data), headers={'User-Agent': 'Testing Browser'})
    assert r.status == 201, await r.text()
    data = await r.json()
    assert data == {'status': 'enquiry submitted to TutorCruncher'}
    assert other_server.app['request_log'] == [
        ('grecaptcha_post', {
            'secret': 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
            'response': 'goodgoodgoodgoodgood'
        }),
        ('enquiry_post', {
            'client_name': 'Cat Flap',
            'client_phone': '123',
            'user_agent': 'Testing Browser',
            'ip_address': None,
            'http_referrer': None}
         )
    ]


async def test_post_enquiry_bad_captcha(cli, company, other_server):
    data = {
        'client_name': 'Cat Flap',
        'client_phone': '123',
        'grecaptcha_response': 'bad_' * 5,
    }
    url = cli.server.app.router['enquiry'].url_for(company=company.public_key)
    r = await cli.post(url, data=json.dumps(data), headers={'X-Forward-For': '1.2.3.4'})
    assert r.status == 201, await r.text()
    assert other_server.app['request_log'] == [
        ('grecaptcha_post', {
            'secret': 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
            'response': 'bad_bad_bad_bad_bad_',
            'remoteip': '1.2.3.4'
        }),
    ]


async def test_post_enquiry_wrong_captcha_domain(cli, company, other_server):
    data = {
        'client_name': 'Cat Flap',
        'client_phone': '123',
        'grecaptcha_response': 'good' * 5,
    }
    other_server.app['grecaptcha_host'] = 'other.com'
    url = cli.server.app.router['enquiry'].url_for(company=company.public_key)
    r = await cli.post(url, data=json.dumps(data), headers={'User-Agent': 'Testing Browser'})
    assert r.status == 201, await r.text()
    assert other_server.app['request_log'] == [
        ('grecaptcha_post', {
            'secret': 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
            'response': 'goodgoodgoodgoodgood'
        })
    ]
