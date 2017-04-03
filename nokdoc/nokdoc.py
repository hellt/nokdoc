import json
import os
import re
import time
import zipfile
import string
from datetime import date
from pprint import pprint

import certifi
import click
import requests
import tqdm
import yaml
from jinja2 import Environment, PackageLoader
from natsort import natsorted, ns

# disable unverified SSL certs warning
# which occurs for infoproducts.alcatel-lucent.com server
# requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# entry point for un-auth access to docs -- https://support.alcatel-lucent.com/portal/web/support
# then go select some product and click on Manual and guides section
# this will open https://infoproducts.alcatel-lucent.com/cgi-bin/doc_list.pl
# where with code explorer it is possible to see all the actual doc_name == doc_id pairs.
doc_id = {'nuage-vsp': '1-0000000000662',
          'nuage-vns': '1-0000000004080',
          'nuage': ['1-0000000000662', '1-0000000004080'],
          '1350oms': '1-0000000003304',
          '7850vsa': '1-0000000004076',
          '7850vsg': '1-0000000004076',
          '7850-8vsg': '1-0000000000459',
          '5620sam': '1-0000000002372',
          '7210sas': '1-0000000003348',
          '7450ess': '1-0000000002317',
          '7705sar': '1-0000000002735',
          '7750sr': '1-0000000002238',
          '7950xrs': '1-0000000003922',
          'vsr': '1-0000000004075'
          }

# correlation between short names of formats as they passed in cli
# and their longer names as they go into HTTP requests.
# TODO: add mobi and epub formats to html composer
formats = {'zip': 'Zip Collection',
           'html': 'HTML',
           'pdf': 'PDF',
           'epub': 'ePub',
           'mobi': 'MOBI'}


# global proxy setting. Proxy can be specified with
# nokdok -p http://ip:port command
# by default no proxy is used
# when issued on NokiaNet no proxy is needed since doc portal resolves to
# internal address
proxies = {'https': ''}

# API endpoint for querying docs
get_doc_url = 'https://infoproducts.alcatel-lucent.com/cgi-bin/get_doc_list.pl'


def user_auth(s, login, pwd):
    """
    Logs in a user and stores session coockies for further tasks
    """

    click.echo('  Logging you in...')
    login_url = 'https://market.alcatel-lucent.com/login.fcc'

    p = {'USERNAME': login,
         'PASSWORD': pwd,
         'Login': 'Log in',
         'TARGET': 'https://market.alcatel-lucent.com/release/employee/SPEmployeeLoginRedirectSvlt?SP_PAGE_ID=0&FINAL_TARGET=https%3A%2F%2Fsupport.alcatel-lucent.com%2Fportal%2Fweb%2Fsupport',
         'USER': login}
    r = s.post(login_url, params=p)
    if 'function checkUserName' in r.text:
        click.echo('  Login failed. Check login/password combination.')
        os.sys.exit()
    else:
        click.echo('  Logged in successfully!')
        return s

def id_generator(size=3, chars=string.ascii_uppercase + string.digits):
    import random
    return ''.join(random.sample(chars, size))

@click.pass_context
def parseDocdata(ctx, rawDoc):
    """
    Parses a raw HTML document which comes as a reply from a GET request
    towards the documentation server.
    Returns a list with dicts where each dict represents a single doc
    entry with its properties
    """

    # using thts link no login required to get the list of nuage docs
    # but that list wont have links to HTML docs, only PDFs
    # though we can construct links to HTML by having doc_id only
    # https://infoproducts.alcatel-lucent.com/cgi-bin/get_doc_list.pl?&entry_id=1-0000000000662&srch_how=Full%20Text&srch_str=&release=4.0.R6.1

    # with this link you get both PDF and HTML links for nuage family
    # but it requires login and have no info about restricted status of docs
    # https://infoproducts.alcatel-lucent.com/aces/cgi-bin/au_get_doc_list.pl?&entry_id=1-0000000000662&srch_how=Full%20Text&srch_str=&release=4.0.R6.1

    doc_list = []
    td_contents_patt = re.compile(r'<td.+?>(.+?)</td>')

    # raw doc comes as html in a string without newlines
    # to parse doc data which is in each <tr> I am inserting newlines
    raw_doc_entries = rawDoc.replace('<tr ', '\n <tr ').split('\n')

    # switch to show notification about restriced documents
    show_restricted_docs_notification = True

    for raw_entry in raw_doc_entries:
        doc_data = {}  # dict to hold doc data for one particular entry

        # this misterious additional symbols in responce data appeared again
        # now they messed with </td> tag in responce for nuage-vsp rel 4.0.r5
        # refer to this output https://regex101.com/r/1KdJHJ/2
        # and look for matched result
        # when requesting data from browser I cant see any bogus symbols
        # same issue was the reason to create get_json_resp() function
        # TODO: this is not 100% reproducable. Analyze later and create an issue
        # as a workaroung I will validate every </td>
        raw_entry = re.sub(r'</t\S*d>', '</td>', raw_entry)

        # example: https://regex101.com/r/NhwnOp/1
        td_contents = td_contents_patt.findall(raw_entry)
        if td_contents:
            if 'a login is required for access' in td_contents[1] \
                    and not ctx.obj['LOGGED_IN']:
                if show_restricted_docs_notification:
                    click.echo('    The following documents are available to logged in users only. They will not be included in the documentation set...')
                    show_restricted_docs_notification = False
                click.echo('      ' + td_contents[0].strip())
                continue
            # click.echo('Adding doc {}'.format(td_contents[0]))
            doc_data.update(parse_td(raw_td=td_contents))

            # when dealing with combined product some docs might be in
            # both sections. Append only unique docs.
            if doc_data not in doc_list:
                doc_list.append(doc_data)
    # pprint(doc_list)
    # os.sys.exit()
    return doc_list


@click.pass_context
def parse_td(ctx, raw_td):
    """
    Dissects given <td> elements from a singe <tr> element. A single <tr>
    element represents a single document and its properties.
    Returns a dict with key as doc_id and value as a dict with doc properties
    """
    d = {}

    # remove html elements from doc_id field
    # key = re.sub('<nobr>|</nobr>', '', raw_td[1]).strip()
    # key is doc_id
    key = re.search(r'>(.*?)<', raw_td[1]).group(1).strip()

    # collect info if a doc is restricted to later show lock icon in HTML
    # for those docs which are with a restricted access
    if 'a login is required for access' in raw_td[1]:
        is_restricted = True
    else:
        is_restricted = False

    d[key] = {'title': raw_td[0].strip(),
              'issue': raw_td[2].strip(),
              'issue_date': re.sub('<nobr>|</nobr>', '', raw_td[3]).strip(),
              'links': parse_td_links(raw_links=raw_td[4], doc_id=key),
              'restricted': is_restricted
              }
    return d


@click.pass_context
def parse_td_links(ctx, raw_links, doc_id):
    """
    Parsing links contained in the last <td> elements.
    returns: list of tuples
    i.e. [(url, type), (url, type)]
    """
    links = []
    # https://regex101.com/r/7iAqds/1
    links_n_types_patt = re.compile(r"href='(.*?)'.*?title='(.*?)'")
    for url_n_type in links_n_types_patt.findall(raw_links):
        link = url_n_type[0]
        l_type = None  # link type
        if 'PDF' in url_n_type[1].upper():
            l_type = 'PDF'
        elif 'ZIP' in url_n_type[1].upper():
            l_type = 'ZIP'
        elif 'HTML' in url_n_type[1].upper():
            l_type = 'HTML'

            # for nuage products I need to construct HTML href manually
            # since I use the HTTP API endpoint which has no direct HTML links
            # see comments in parseDocdata() func for further explanation
            if 'nuage' in ctx.obj['PRODUCT']:
                link = 'https://infoproducts.alcatel-lucent.com/aces/htdocs/{}/index.html'.format(doc_id)

        links.append((link, l_type))
    return links


def create_doc_html(docs_list, product, release):
    click.echo('\n  Building HTML with the docs you requested...')

    # gluing filename
    fname = 'nokdoc__{}'.format(product.upper())
    if release:
        fname += '__{}'.format(release.upper().replace(' ', '_'))
    # Is it of any good to put generation date in filename?
    # fname += '__{}'.format(date.today().strftime("%Y_%m_%d"))
    fname += '.html'

    env = Environment(loader=PackageLoader('nokdoc', 'template'),
                      trim_blocks=True,
                      lstrip_blocks=True)
    template = env.get_template('nokdoc_docset.html')
    with open(fname, 'w') as f:
        html = template.render(docs_list=docs_list, product=product,
                               release=release,
                               gen_date=date.today().strftime("%Y/%m/%d"))
        f.write(html)
    click.echo('  Done! File created:\n   ->{}'
               .format(os.path.join(os.path.abspath(os.path.curdir),
                                    fname)))


def get_rels(s, product_id):
    '''
    returns a list of available releases for a given product
    '''
    params = {'entry_id': product_id}
    return requests.get(get_doc_url, params=params).json()['proddata']['release']


def get_common_rels(s, product_ids):
    """
    When working with combined product (like 'nuage' which consits of nuage-vsp
    and nuage-vns products) it is necessary to define which releases are common
    for every component.
    """
    common_rels = {}
    for i, product_id in enumerate(product_ids):
        if i == 0:
            common_rels = set(get_rels(s, product_id))
        common_rels.intersection_update(set(get_rels(s, product_id)))
    return sorted(common_rels)


def download_doc(s, dwnld_doc_url, remote_fname, username, local_fname):
    """
    Downloads a collection zip file and stores it in the same dir
    where nokdoc script was executed.
    """
    i = 1
    while i != 30:
        click.echo('  Waiting for the documentation server to prepare the archive. Attempt #{}'.format(i))
        r = s.get(dwnld_doc_url, stream=True)
        if r.status_code != requests.codes.ok:
            click.echo('  !! Server encountered an error'
                       ' with the code {}. Aborting'. format(r.status_code))
            os.sys.exit()
        if r.headers['Content-type'] != 'archive/zip':
            time.sleep(5)
            i += 1
        else:
            total_dwnld_size = int(get_coll_size(s, remote_fname, username)) // 1024
            with open(local_fname, 'wb') as f:
                for data in tqdm.tqdm(r.iter_content(chunk_size=1024),
                                      unit='K', total=total_dwnld_size):
                    f.write(data)
                click.echo('\n  File has been downloaded successfully '
                           'to the following '
                           'location\n   -> {}'.format(os.path.join(
                                                       os.path.abspath(os.path.curdir),
                                                       local_fname)))
            break


def get_coll_size(s, fname, username):
    """
    Determines a size of downloadable collection.
    Needed for progress bar.
    """
    chk_size_url = 'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/chk_col_done.pl'
    params = {'remote_user': username,
              'col_name': fname}
    resp = s.get(chk_size_url, params=params).json()
    fsize = resp['filesize']
    # fsize is smth like (56,950,085 bytes)
    # stripping everything except digits
    fsize_parsed = re.sub('[^\d]', '', fsize)
    return fsize_parsed


def is_empty_list(in_list):
    """
    https://stackoverflow.com/questions/1593564/python-how-to-check-if-a-nested-list-is-essentially-empty
    Recursively iterate through values in nested lists and return boolean
    reflecting if the list and its nested elements are empty.
    """
    for item in in_list:
        if not isinstance(item, list) or not is_empty_list(item):
            return False
    return True


def get_json_resp(responce):
    '''
    Sometimes documentation server returns junk data before
    json responce. This will raise decode exception.
    Strip this data if any
    for example this one gives trouble if using .json() instead
    nokdoc -l rdodin getlinks -p nuage-vns -r 4.0.r6
    '''
    try:
        json_resp = responce.json()
        return json_resp
    except json.decoder.JSONDecodeError:
        json_str = re.search(r'{.*}', responce.text, flags=re.DOTALL).group()
        json_str = json_str.replace('\n', '').replace('\r', '')
        json_resp = json.loads(json_str)
    return json_resp


def validate_product(ctx, param, value):
    # global get_doc_url
    if 'nuage' in value:
        # # nuage API endpoint for fetching links differs from others
        # get_doc_url = 'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/au_get_doc_list.pl'

        # quit if no login was passed for Nuage docs
        if not ctx.obj['LOGGED_IN']:
            click.echo('  Nuage Networks documentation can be accessed by authorized users only!\n'
                       '  Pass your login as "-l your_login" if you have one.\n'
                       '  Aborting...')
            os.sys.exit()
    return value


@click.group()
@click.pass_context
# @click.command()
@click.option('-l', '--login', help='Put in your login to get access to the'
              'documentation requiring authorization')
@click.option('-p', '--proxy', default='')
def cli(ctx, proxy, login):
    """
    NokDoc CLI Tool is exposing a set of commands to interact with
    Nokia documentation portal.
    It offers CLI experience for tasks like
    - getting links to the docs aggregated into HTML file
    - downloading docs collections automatically

    It works for authorized users and guests.
    """

    ctx.obj = {'LOGGED_IN': False}
    # defining a proxy
    if proxy:
        proxies['https'] = proxy
    # creating requests session object
    s = requests.session()
    s.proxies.update(proxies)
    s.verify = certifi.where()
    # buiding a context object to pass session object

    # log in and get cookies to get "protected" docs
    if login:
        click.echo('\n  ####### LOGIN #######')
        pwd = click.prompt('  Please enter your password for a "{}" user'.format(login), hide_input=True)
        s = user_auth(s, login, pwd)
        ctx.obj['LOGGED_IN'] = True
        ctx.obj['USERNAME'] = login

    ctx.obj['SESSION'] = s


@cli.command()
@click.pass_context
# https://github.com/pallets/click/issues/514 required=True
@click.option('-p', '--product', type=click.Choice(sorted(doc_id.keys())),
              required=True, callback=validate_product)
@click.option('-r', '--release',
              default='',
              help='Release version, use "showrels" command to list them')
@click.option('-f', '--format', help='Specify documentation format to fetch.'
              'If unspecified -> all types will be collected.',
              type=click.Choice(['pdf', 'html', 'zip']))
@click.option('-s', '--sort', default='title',
              type=click.Choice(['title', 'issue_date']),
              help='Choose sorting key. Defaults to "title"')
def getlinks(ctx, product, release, format, sort):
    '''
    Gets a single HTML file with links to the documetation elements for a given
    product.
    '''
    click.echo('\n  ####### GET LINKS #######')

    global doc_id
    global get_doc_url
    # xpin = '''<div><table style='width: 100%;border-collapse:collapse'><tbody><tr style='border-top: 1px solid black !important;border-bottom: 1px solid black !important;'><th style='text-align: left;width: 55%;'>Title</th><th style='text-align: left;width: 12%;'>Document</th><th>Issue&#160;&#160;&#160;</th><th style='text-align: center;'>Issue Date</th><th style='text-align: left;'>Format</th></tr><tr style='background-color:#E9E9E9;' > <td style='font-weight: 600'>7450 ESS and 7750 SR Troubleshooting Guide </td><td style='size: 140px;font-weight: 500'><nobr>3HE 11475 AAAA TQZZA 01 <img title='Key means document is restricted and a login is required for access.' src='/images/prodcontent_key.gif'></nobr></td> <td style='text-align:center' class='T5'>1</td> <td style='text-align:center' class='T5'><nobr>Dec 8, 2016</nobr></td> <td><nobr>&#160;&#160;<a href='https://infoproducts.alcatel-lucent.com/aces/cgi-bin/au_doc_list.pl?entry_id=1-0000000002238&srch_how=Title&release=14.0' target='_self' ><img src='/images/pdficon.jpg' title='PDF document' width='20' height='20' style='border-style:none'></a></nobr></td></tr><tr style='background-color:#FFFFFF;' > <td style='font-weight: 600'>7450 ESS, 7750 SR, and 7950 XRS Multicast Routing Protocols Guide R14.0.R4 </td><td style='size: 140px;font-weight: 500'><nobr>3HE 10795 AAAB TQZZA 02 </nobr></td> <td style='text-align:center' class='T5'>2</td> <td style='text-align:center' class='T5'><nobr>Dec 2, 2016</nobr></td> <td><nobr>&#160;&#160;<a href='https://infoproducts.alcatel-lucent.com/cgi-bin/dbaccessfilename.cgi/3HE10795AAABTQZZA02_V1_7450 ESS 7750 SR and 7950 XRS Multicast Routing Protocols Guide R14.0.R4.pdf' target='_blank' ><img src='/images/pdficon.jpg' title='PDF document' width='20' height='20' style='border-style:none'></a></nobr></td></tr>
    # '''
    # root = html.fromstring(xpin)
    # tmp = root.xpath('//td//text()|//a/@href')
    # arr = [tmp[i:i + 6] for i in range(0, len(tmp), 6)]
    # pprint(arr)

    # mapping of cli options for sotring and values for API calls
    sort_opts = {'title': 'Title, A-Z',
                 'issue_date': 'Issue Date'}

    # used to map cli short_format notation to long_format which is passed to request
    long_format = ''
    # if format option is specified, rewrite acting format value
    if format:
        long_format = formats[format]

    # for nuage family 'get_doc_url' URL differs from 7750
        # get_doc_url = 'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/au_get_doc_list.pl'

    click.echo('  Querying the documentation server '
               'for {} release {}...'.format(product, release))

    # list with requests responces
    responces = []

    params = {'entry_id': doc_id[product],
              'release': release.upper(),
              'format': long_format,
              'sortby': sort_opts[sort]
              }

    # if we are dealing with composed doc section (like 'nuage')
    # go through every enclosed doc_id and populate a list with responces
    if type(doc_id[product]) is list:
        for entry_id in doc_id[product]:
            # redefine entry_id
            params.update({'entry_id': entry_id})
            # pprint(params)
            responces.append(get_json_resp(ctx.obj['SESSION'].get(get_doc_url, params=params)))
    else:
        responces.append(get_json_resp(ctx.obj['SESSION'].get(get_doc_url, params=params)))
        # responces.append(ctx.obj['SESSION'].get(get_doc_url, params=params).json())
    # with open('nuage.txt', 'w') as f:
    #     print(responces, file=f)
    #     pprint(responces, stream=f)
    # os.sys.exit()

    # if no results were found format section will be empty
    if is_empty_list([i['proddata']['format']
                      for i in responces]):
        click.echo('  No documents were found with the specified criteria. Exiting...')
        os.sys.exit()

    # num_docs_found_patt = re.compile(r"'>(\d+.+)</td")
    # num_docs_found = num_docs_found_patt.search(r['proddata']['doc_summary']).group(1)
    # click.echo('    ' + num_docs_found)

    docdata = ''
    for i in responces:
        docdata += i['proddata']['docdata']

    click.echo('\n  Checking documentation access rights...')

    ctx.obj['PRODUCT'] = product
    docs_list = parseDocdata(docdata)

    # if doc_list is empty --> abort
    if not docs_list:
        click.echo('  Either all of the docs are for authorized users only\n'
                   '  or your search request returned no valid results.\n'
                   '  Execution aborted.')
        os.sys.exit(1)

    create_doc_html(docs_list, product, release)

# root = html.fromstring(r.json()['proddata']['docdata'])
# tmpList = root.xpath('//td//text()|//a/@href')
# # slicing list of xpathed data to "list per document"
# # 6 is the number of elements per doc entry
# # refer to docdata html chunck, i.e.https://infoproducts.alcatel-lucent.com/cgi-bin/get_doc_list.pl?entry_id=1-0000000002238&srch_how=Title&srch_str=&release=14.0
# # beautify it with http://www.cleancss.com/html-beautify/ and count <td> elements in each <tr>
# # https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
# docList = [tmp[i:i + 6] for i in range(0, len(tmp), 6)]


@cli.command()
@click.pass_context
@click.option('-p', '--product', type=click.Choice(sorted(doc_id.keys())),
              required=True)
def showrels(ctx, product):
    """
    Lists all available releases for a given product
    """

    click.echo('\n  ####### SHOW RELEASES #######')

    click.echo('  Checking available releases...')

    if type(doc_id[product]) is list:
        rels = get_common_rels(ctx.obj['SESSION'], doc_id[product])
    else:
        rels = get_rels(ctx.obj['SESSION'], doc_id[product])
    click.echo('  Available releases for {} family: '.format(product) +
               ', '.join(natsorted(rels, alg=ns.IGNORECASE)))


@cli.command()
@click.pass_context
@click.option('-p', '--product', type=click.Choice(sorted(doc_id.keys())),
              required=True, callback=validate_product)
@click.option('-r', '--release',
              default='',
              help='Release version, use "showrels" command to list them')
@click.option('-f', '--format', help='Specify documentation format to fetch.'
              'If unspecified -> all types will be collected.', type=click.Choice(['pdf', 'html', 'zip']))
def getdocs(ctx, product, release, format):
    '''
    Downloads documentation collection for a given product family.
    Optionally specify release version to fetch
    OPtionally specify format of the docs to fetch

    Currently supported products: nuage, nuage-vsp, nuage-vns
    '''

    click.echo('\n  ####### DOWNLOAD DOCS #######')
    global doc_id

    dwnld_doc_url = 'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/create_col.pl'

    # used to map cli short_format notation to long_format which is passed to request
    long_format = ''
    # if format option is specified, rewrite acting format value
    if format:
        long_format = formats[format]

    data = {'entry_id': doc_id[product],
            'release': release.upper(),
            'format': long_format,
            'create_col_flg': '1'}

    r = ctx.obj['SESSION'].post(dwnld_doc_url, data=data)

    # with open('test.html', 'w') as f:
    #     print(r.text, file=f)

    doc_dwnld_url = ''

    # slicing last 100 lines where download link should be
    for line in r.text.splitlines()[-100:]:
        if 'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/down_col.pl' in line:
            doc_dwnld_url = re.search(r'https://infoproducts.alcatel-lucent.com/aces/cgi-bin/down_col.pl?.*\.zip', line).group()

            # get file name without .zip extension to query for coll. dwnld size
            remote_fname = doc_dwnld_url.rsplit('=')[1][:-4]

            click.echo('  Collection will be available for download '
                       'by this URL for the next 48hrs \n   -> {}\n'.format(doc_dwnld_url))
            break

    # gluing filename
    local_fname = 'nokdoc__{}'.format(product.upper())
    if release:
        local_fname += '__{}'.format(release.upper().replace(' ', '_'))
    if format:
        local_fname += '__{}'.format(format.upper())
    else:
        local_fname += '__ALL'
    local_fname += '__{}.zip'.format(date.today().strftime("%Y_%m_%d"))

    download_doc(ctx.obj['SESSION'], doc_dwnld_url, remote_fname, ctx.obj['USERNAME'],
                 local_fname)


@cli.command()
@click.pass_context
@click.argument('finput')
def batchgetlinks(ctx, finput):
    '''
    Invokes getlinks command for a list of products/releases defined in
    a YAML file passed as argument
    '''
    click.echo('\n  ####### BATCH GET LINKS #######')

    with click.open_file(finput, 'r') as f:
        products = yaml.load(f)   # load getlinks product/rels file

    # create a 'docs' dir which will hold enclosed dirs with docs per product
    if not os.path.isdir('docs'):
        os.mkdir('docs')
    os.chdir('docs')

    for product in products:
        if not os.path.isdir(product):
            os.mkdir(product)
        os.chdir(product)
        # pprint(os.getcwd())

        for release in products[product]['releases']:
            ctx.obj['PRODUCT'] = product
            # pprint(product + " " + release)
            if release is None:
                release=''
            ctx.invoke(getlinks, product=product, release=release)
        os.chdir('..')


def filename_formatter(s):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in s if c in valid_chars)
    filename = filename.replace(' ', '_')
    return filename


@cli.command()
@click.pass_context
@click.option('-p', '--path', default='.',
              help='Path to the zip archive or to directory with unzipped Nuage docs folders')

def htmlfix(ctx, path):
    '''
    Renames Nuage documentation directories from DOC-ID to TITLE
    '''

    import shutil
    # import zlib

    orig_cwd = os.path.abspath(os.path.curdir)
    path_dir = os.path.abspath(os.path.dirname(path))

    def fix_contents(dir_path):
        """
        Renaming docs dirs function
        """
        # regexp to match human readable doc name
        re_html_title = re.compile(r'<title>(.+)&mdash')

        # move to the temp dir
        os.chdir(dir_path)

        for doc_section_dir in os.listdir(os.curdir):
            if os.path.isdir(doc_section_dir):
                content = open(os.path.join(os.curdir, doc_section_dir, "index.html"), encoding="utf8").read()
                try:
                    new_dirname = filename_formatter(re_html_title.search(content).group(1).strip())
                except AttributeError:
                    break
                os.renames(os.path.join(os.curdir, doc_section_dir), os.path.join(os.curdir, new_dirname))

    def get_all_file_paths(directory):
        """
        Recursively walk the directory and get paths
        to the files inside
        """
        # initializing empty file paths list
        file_paths = []
        click.echo(directory)
        # crawling through directory and subdirectories
        for root, _, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                file_paths.append(filepath)
        # returning all file paths
        return file_paths

    click.echo('\n  ####### HTML DOC FIX #######')

    if zipfile.is_zipfile(path):
        click.echo('\n  Processing a zip archive "{}"...'.format(path))

        os.chdir(path_dir)

        # creating a temp dir to store unarchived data
        tmp_dir_name = 'tmp_nokdoc_docs_{}'.format(id_generator())
        os.mkdir(tmp_dir_name)
        tmpdir_abspath = os.path.abspath(tmp_dir_name)

        with zipfile.ZipFile(path, "r") as zf:
            try:
                zf.extractall(tmpdir_abspath)
                click.echo('  Successfully unzipped documentation archive...')
            except:
                print('Could not unarchive the zip file')

        # fix dir names
        time.sleep(2)
        fix_contents(tmpdir_abspath)

        new_arch_fname = path
        new_arch_abspath = os.path.join(path_dir, new_arch_fname)

        with zipfile.ZipFile(new_arch_abspath, "w", compression=zipfile.ZIP_DEFLATED) as zfw:
            try:
                click.echo('  Archiving renamed documents...')
                [zfw.write(x) for x in get_all_file_paths(os.curdir)]
            except:
                click.echo('  Failed to archive the zip file')

        # deleting temp directory and files
        click.echo('  Removing temporary files...')

        # return to the original working directory
        # and delete the temp dir
        os.chdir(path_dir)
        try:
            shutil.rmtree(tmpdir_abspath)
        except PermissionError:
            click.echo('  Unable to remove temp directory')

        click.echo('  Successfully created archive with renamed documents!'
                   '\n    --> {}'.format(new_arch_abspath))

    # option2: process directory with docs
    if os.path.isdir(path):
        click.echo('\n  Processing a directory "{}" with docs inside...'.format(path))
        fix_contents(os.path.abspath(path))
        click.echo('  Renamed doc dirs in the "{}" directory...'.format(os.path.abspath(path)))
