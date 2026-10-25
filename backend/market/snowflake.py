"""Minimal Snowflake REST client: the SQL API (/api/v2/statements) and Cortex REST (/api/v2/cortex/inference:complete),
authenticated with a programmatic access token."""
import asyncio
import httpx


class SnowflakeError(Exception):
    pass


def binding(value):
    if isinstance(value, bool) or value is None:
        return {'type': 'TEXT', 'value': None if value is None else str(value)}
    if isinstance(value, (int, float)):
        return {'type': 'REAL', 'value': str(value)}
    return {'type': 'TEXT', 'value': str(value)}


class Snowflake:
    def __init__(self, settings, timeout=45):
        self.settings, self.timeout = settings, timeout

    @property
    def enabled(self):
        return bool(self.settings.snowflake_account_url and self.settings.snowflake_pat)

    def _client(self):
        return httpx.AsyncClient(base_url=self.settings.snowflake_account_url.rstrip('/'), timeout=self.timeout, headers={
            'Authorization': f'Bearer {self.settings.snowflake_pat}',
            'X-Snowflake-Authorization-Token-Type': 'PROGRAMMATIC_ACCESS_TOKEN',
            'Content-Type': 'application/json', 'Accept': 'application/json'})

    async def sql(self, statement, params=(), database=True):
        """Rows as lists of strings (Snowflake's JSON format). `?` placeholders bind `params` in order."""
        body = {'statement': statement, 'warehouse': self.settings.snowflake_warehouse, 'timeout': self.timeout,
                'bindings': {str(i + 1): binding(v) for i, v in enumerate(params)}}
        if database:
            body.update(database=self.settings.snowflake_database, schema='MARKET')
        async with self._client() as http:
            response = await http.post('/api/v2/statements', json=body)
            data = response.json()
            for _ in range(60):  # a long statement answers 202 with a handle to poll
                if response.status_code != 202:
                    break
                await asyncio.sleep(.5)
                response = await http.get(f"/api/v2/statements/{data['statementHandle']}")
                data = response.json()
        if response.status_code != 200:
            raise SnowflakeError(data.get('message') or f'HTTP {response.status_code}')
        return data.get('data') or []

    async def complete(self, prompt, max_tokens=120):
        async with self._client() as http:
            response = await http.post('/api/v2/cortex/inference:complete', json={
                'model': self.settings.snowflake_model, 'max_tokens': max_tokens, 'stream': False,
                'messages': [{'role': 'user', 'content': prompt}]})
        data = response.json()
        if response.status_code != 200 or not data.get('choices'):
            raise SnowflakeError(data.get('message') or f'HTTP {response.status_code}')
        return (data['choices'][0]['message'].get('content') or '').strip()
