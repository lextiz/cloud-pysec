from sap.xssec import constants
from sap.xssec.key_cache import KeyCache, CacheEntry
from mock import patch, MagicMock
import unittest

from tests.http_responses import *

MOCKED_CURRENT_TIME = 915148801.25
threadErrors = False


@patch('time.time', return_value=MOCKED_CURRENT_TIME)
@patch('requests.get')
class CacheTest(unittest.TestCase):

    def setUp(self):
        self.cache = KeyCache()
        self.mock = MagicMock()

    def test_empty_cache_load_key(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS

        key = self.cache.load_key("jku1", "key-id-1")

        self.assert_key_equal(KEY_ID_1, key)
        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def test_not_hit_load_key(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        self.cache._cache[KeyCache._create_cache_key("jku2", "key-id-1")] = CacheEntry("dummy-key", MOCKED_CURRENT_TIME)

        key = self.cache.load_key("jku1", "key-id-1")

        self.assert_key_equal(KEY_ID_1, key)
        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def test_hit_do_not_load_key(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        self.cache._cache[KeyCache._create_cache_key("jku1", "key-id-1")] = CacheEntry("dummy-key", MOCKED_CURRENT_TIME -
                                                                                       (constants.KEYCACHE_DEFAULT_CACHE_ENTRY_EXPIRATION_TIME_IN_MINUTES - 1) * 60)

        key = self.cache.load_key("jku1", "key-id-1")

        self.assert_key_equal("dummy-key", key)
        self.assertFalse(mock_requests.called)

    def test_expired_key_load_key(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        self.cache._cache[KeyCache._create_cache_key("jku1", "key-id-1")] = CacheEntry("dummy-key",
                                                                                       MOCKED_CURRENT_TIME -
                                                                                       (constants.KEYCACHE_DEFAULT_CACHE_ENTRY_EXPIRATION_TIME_IN_MINUTES + 1) * 60)

        key = self.cache.load_key("jku1", "key-id-1")

        self.assert_key_equal(KEY_ID_1, key)
        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def test_kid_does_not_match(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        self.cache._cache[KeyCache._create_cache_key("jku2", "key-id-1")] = CacheEntry("dummy-key", MOCKED_CURRENT_TIME)

        key = self.cache.load_key("jku2", "key-id-0")

        self.assert_key_equal(KEY_ID_0, key)
        mock_requests.assert_called_once_with("jku2", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def test_cache_max_size(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        for i in range(0, constants.KEYCACHE_DEFAULT_CACHE_SIZE):
            self.cache._cache[KeyCache._create_cache_key("jku-" + str(i), "key-id-1")] = CacheEntry("dummy-key", MOCKED_CURRENT_TIME)
        self.assertEqual(len(self.cache._cache), constants.KEYCACHE_DEFAULT_CACHE_SIZE)
        self.assertTrue(KeyCache._create_cache_key("jku-0", "key-id-1") in self.cache._cache)

        key = self.cache.load_key("jku1", "key-id-0")

        self.assert_key_equal(KEY_ID_0, key)
        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)
        self.assertEqual(len(self.cache._cache), constants.KEYCACHE_DEFAULT_CACHE_SIZE)
        # assert that least recently inserted key got deleted
        self.assertFalse(KeyCache._create_cache_key("jku-0", "key-id-1") in self.cache._cache)

    def test_update_increases_insertion_order(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS
        for i in range(0, constants.KEYCACHE_DEFAULT_CACHE_SIZE):
            self.cache._cache[KeyCache._create_cache_key("jku-" + str(i), "key-id-1")] = CacheEntry("dummy-key", MOCKED_CURRENT_TIME)
        self.assertEqual(len(self.cache._cache), constants.KEYCACHE_DEFAULT_CACHE_SIZE)
        self.assertTrue(KeyCache._create_cache_key("jku-0", "key-id-1") in self.cache._cache)

        # first cache entry is invalid -> must be updated
        self.cache._cache[KeyCache._create_cache_key("jku-0", "key-id-1")].insert_timestamp = 0

        # update first cache entry -> should not deleted if new key is added
        self.cache.load_key("jku-0", "key-id-1")
        self.assertTrue(KeyCache._create_cache_key("jku-0", "key-id-1") in self.cache._cache)
        self.assertTrue(KeyCache._create_cache_key("jku-1", "key-id-1") in self.cache._cache)

        # add new key
        self.cache.load_key("jku1", "key-id-0")

        self.assertTrue(KeyCache._create_cache_key("jku-0", "key-id-1") in self.cache._cache)
        self.assertFalse(KeyCache._create_cache_key("jku-1", "key-id-1") in self.cache._cache)
        self.assertEqual(len(self.cache._cache), constants.KEYCACHE_DEFAULT_CACHE_SIZE)

    @patch('sap.xssec.key_cache.CacheEntry.is_valid', return_value=False)
    def test_parallel_access_works(self, mock_valid, mock_requests, mock_time):
        # All entries are invalid, so each load updates the cache.
        # This leads to problems if the threads are not correctly synchronized.
        import threading
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS

        def thread_target():
            for _ in range(0, 100):
                try:
                    self.cache.load_key("jku1", "key-id-0")
                except Exception:
                    global threadErrors
                    threadErrors = True
                    raise

        threads = []
        for _ in range(0, 10):
            t = threading.Thread(target=thread_target, args=[])
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(threadErrors)

    def test_get_returns_empty(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = {}

        with self.assertRaises(ValueError):
            self.cache.load_key("jku1", "key-id-1")

        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def test_no_matching_kid(self, mock_requests, mock_time):
        mock_requests.return_value = self.mock
        self.mock.json.return_value = HTTP_SUCCESS

        with self.assertRaises(ValueError):
            self.cache.load_key("jku1", "key-id-3")

        mock_requests.assert_called_once_with("jku1", timeout=constants.HTTP_TIMEOUT_IN_SECONDS)

    def assert_key_equal(self, key1, key2):
        self.assertEqual(strip_white_space(key1), strip_white_space(key2))


def strip_white_space(key):
    return key.replace(" ", "").replace("\t", "").replace("\n", "")
