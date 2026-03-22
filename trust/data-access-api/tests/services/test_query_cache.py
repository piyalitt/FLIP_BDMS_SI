# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from data_access_api.services.query_cache import (
    CacheEntry,
    _cache,
    _make_cache_key,
    clear_cache,
    get_cached_result,
    set_cached_result,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the cache before and after each test."""
    _cache.clear()
    yield
    _cache.clear()


class TestMakeCacheKey:
    def test_deterministic(self):
        key1 = _make_cache_key("SELECT * FROM table")
        key2 = _make_cache_key("SELECT * FROM table")
        assert key1 == key2

    def test_normalizes_whitespace(self):
        key1 = _make_cache_key("SELECT  *   FROM   table")
        key2 = _make_cache_key("SELECT * FROM table")
        assert key1 == key2

    def test_case_insensitive(self):
        key1 = _make_cache_key("SELECT * FROM table")
        key2 = _make_cache_key("select * from table")
        assert key1 == key2

    def test_different_queries_different_keys(self):
        key1 = _make_cache_key("SELECT * FROM table_a")
        key2 = _make_cache_key("SELECT * FROM table_b")
        assert key1 != key2


class TestGetCachedResult:
    @patch("data_access_api.services.query_cache.get_settings")
    def test_returns_none_on_miss(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        result = get_cached_result("SELECT 1")
        assert result is None

    @patch("data_access_api.services.query_cache.get_settings")
    def test_returns_cached_dataframe(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        df = pd.DataFrame({"col": [1, 2, 3]})
        set_cached_result("SELECT 1", df)

        result = get_cached_result("SELECT 1")
        assert result is not None
        pd.testing.assert_frame_equal(result, df)

    @patch("data_access_api.services.query_cache.get_settings")
    def test_returns_copy_not_reference(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        df = pd.DataFrame({"col": [1, 2, 3]})
        set_cached_result("SELECT 1", df)

        result = get_cached_result("SELECT 1")
        result["col"] = [99, 99, 99]

        # Original cached value should be unchanged
        result2 = get_cached_result("SELECT 1")
        pd.testing.assert_frame_equal(result2, df)

    @patch("data_access_api.services.query_cache.get_settings")
    def test_expired_entry_returns_none(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        query = "SELECT 1"
        df = pd.DataFrame({"col": [1]})
        key = _make_cache_key(query)

        # Insert an entry that expired 1 day ago
        _cache[key] = CacheEntry(df=df.copy(), created_at=datetime.now(UTC) - timedelta(days=61))

        result = get_cached_result(query)
        assert result is None
        assert key not in _cache  # Expired entry should be removed


class TestSetCachedResult:
    @patch("data_access_api.services.query_cache.get_settings")
    def test_stores_entry(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        df = pd.DataFrame({"col": [1, 2]})
        set_cached_result("SELECT 1", df)
        assert len(_cache) == 1

    @patch("data_access_api.services.query_cache.get_settings")
    def test_stores_copy(self, mock_settings):
        mock_settings.return_value.CACHE_TTL_DAYS = 60
        df = pd.DataFrame({"col": [1, 2]})
        set_cached_result("SELECT 1", df)

        # Mutating original should not affect cache
        df["col"] = [99, 99]
        result = get_cached_result("SELECT 1")
        assert list(result["col"]) == [1, 2]


class TestClearCache:
    def test_clears_all_entries(self):
        _cache["key1"] = CacheEntry(df=pd.DataFrame(), created_at=datetime.now(UTC))
        _cache["key2"] = CacheEntry(df=pd.DataFrame(), created_at=datetime.now(UTC))
        assert len(_cache) == 2

        clear_cache()
        assert len(_cache) == 0
