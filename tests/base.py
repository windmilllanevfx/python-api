"""Base class for Shotgun API tests."""
import unittest
from ConfigParser import ConfigParser

try:
    import simplejson as json
except ImportError:
    import json as json

import mock
import shotgun_api3 as api

CONFIG_PATH = 'tests/config'

class TestBase(unittest.TestCase):
    '''Base class for tests.
    
    Sets up mocking and database test data.'''
    def __init__(self, *args, **kws):
        unittest.TestCase.__init__(self, *args, **kws)
        self.is_mock        = False
        self.human_user     = None
        self.project        = None
        self.shot           = None
        self.asset          = None
        self.version        = None
        self.human_password = None
        self.server_url     = None
    

    def setUp(self):
        config = SgTestConfig()
        config.read_config(CONFIG_PATH)
        self.human_password = config.human_password
        self.server_url     = config.server_url
        self.script_name    = config.script_name
        self.api_key        = config.api_key
        self.http_proxy     = config.http_proxy
        self.session_uuid   = config.session_uuid

        self.sg = api.Shotgun(config.server_url, config.script_name, 
            config.api_key, http_proxy=config.http_proxy)

        if config.session_uuid:
            self.sg.set_session_uuid(config.session_uuid)
            
        if config.mock:
            self._setup_mock()
            self._setup_mock_data(config)
        else:
            self._setup_db(config)

        
    def tearDown(self):
        self.sg = None
        return
    
    def _setup_mock(self):
        """Setup mocking on the ShotgunClient to stop it calling a live server
        """
        #Replace the function used to make the final call to the server
        #eaiser than mocking the http connection + response
        self.sg._http_request = mock.Mock(spec=api.Shotgun._http_request,
            return_value=((200, "OK"), {}, None))
        
        #also replace the function that is called to get the http connection
        #to avoid calling the server. OK to return a mock as we will not use 
        #it
        self.mock_conn = mock.Mock(spec=api.Http)
        #The Http objects connection property is a dict of connections 
        #it is holding
        self.mock_conn.connections = dict()
        self.sg._connection = self.mock_conn
        self.sg._get_connection = mock.Mock(return_value=self.mock_conn)
        
        #create the server caps directly to say we have the correct version
        self.sg._server_caps = api.ServerCapabilities(self.sg.config.server, 
            {"version" : [2,4,0]})
        self.is_mock = True
        return
        
    def _mock_http(self, data, headers=None, status=None):
        """Setup a mock response from the SG server. 
        
        Only has an affect if the server has been mocked. 
        """
        #test for a mock object rather than config.mock as some tests 
        #force the mock to be created
        if not isinstance(self.sg._http_request, mock.Mock):
            return

        if not isinstance(data, basestring):
            data = json.dumps(data, ensure_ascii=False, encoding="utf-8")
            
        resp_headers = {
            'cache-control': 'no-cache',
            'connection': 'close',
            'content-length': (data and str(len(data))) or 0 ,
            'content-type': 'application/json; charset=utf-8',
            'date': 'Wed, 13 Apr 2011 04:18:58 GMT',
            'server': 'Apache/2.2.3 (CentOS)',
            'status': '200 OK'
        }
        if headers:
            resp_headers.update(headers)
        
        if not status:
            status = (200, "OK")
        #create a new mock to reset call list etc.
        self._setup_mock()
        self.sg._http_request.return_value = (status, resp_headers, data)
        
        self.is_mock = True
        return
    
    def _assert_http_method(self, method, params, check_auth=True):
        """Asserts _http_request is called with the method and params."""
        
        args, _ = self.sg._http_request.call_args
        arg_body = args[2]
        assert isinstance(arg_body, basestring)
        arg_body = json.loads(arg_body)
        
        arg_params = arg_body.get("params")
        
        self.assertEqual(method, arg_body["method_name"])
        if check_auth:
            auth = arg_params[0]
            self.assertEqual(self.script_name, auth["script_name"])
            self.assertEqual(self.api_key, auth["script_key"])
        
        if params:
            rpc_args = arg_params[len(arg_params)-1]
            self.assertEqual(params, rpc_args)
            
        return

    def _setup_mock_data(self, config):
        self.human_user     = { 'id':1, 
                                'login':config.human_login,
                                'type':'HumanUser' }
        self.project        = { 'id':2,
                                'name':config.project_name,
                                'type':'Project' }
        self.shot           = { 'id':3,
                                'code':config.shot_code,
                                'type':'Shot' }
        self.asset          = { 'id':4,
                                'code':config.asset_code,
                                'type':'Asset' }
        self.version        = { 'id':5,
                                'code':config.version_code,
                                'type':'Version' }

    def _setup_db(self, config):
        data = {'name':config.project_name}
        self.project = _find_or_create_entity(self.sg, 'Project', data)
        
        data = {'name':config.human_name,
                'login':config.human_login,
                'password_proxy':config.human_password}
        self.human_user = _find_or_create_entity(self.sg, 'HumanUser', data)

        data = {'code':config.asset_code,
                'project':self.project}
        keys = ['code']
        self.asset = _find_or_create_entity(self.sg, 'Asset', data, keys)
        
        data = {'project':self.project,
                'code':config.version_code,
                'entity':self.asset,
                'user':self.human_user}
        keys = ['code','project']
        self.version = _find_or_create_entity(self.sg, 'Version', data, keys)
        
        keys = ['code','project']
        data = {'code':config.shot_code,
                'project':self.project}
        self.shot = _find_or_create_entity(self.sg, 'Shot', data, keys)



def _find_or_create_entity(sg, entity_type, data, identifyiers=None):
    '''Finds or creates entities.
    @params:
        sg           - shogun_json.Shotgun instance
        entity_type  - entity type
        data         - dictionary of data for the entity
        identifyiers -list of subset of keys from data which should be used to 
                      uniquely identity the entity
    @returns dicitonary of the entity values
    '''
    identifyiers = identifyiers or ['name']
    fields = data.keys() 
    filters = [[key, 'is', data[key]] for key in identifyiers]
    entity = sg.find_one(entity_type, filters, fields=fields)
    entity = entity or sg.create(entity_type, data, return_fields=fields)
    assert(entity)
    return entity

class SgTestConfig(object):
    '''Reads test config and holds values'''
    def __init__(self):
        self.mock           = True
        self.server_url     = None  
        self.script_name    = None  
        self.api_key        = None  
        self.http_proxy     = None  
        self.session_uuid   = None  
        self.project_name   = None  
        self.human_name     = None  
        self.human_login    = None  
        self.human_password = None  
        self.asset_code     = None  
        self.version_code   = None  
        self.shot_code      = None  

    def read_config(self, config_path):
        config_parser = ConfigParser()
        config_parser.read(config_path)
        for section in config_parser.sections():
            for option in config_parser.options(section):
                value = config_parser.get(section, option)
                setattr(self, option, value)
        # cast non-sting attributes
        self.mock = 'True' == str(self.mock)

