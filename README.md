# Pydantic Consul settings

[![PyPI version](https://img.shields.io/pypi/v/pydantic-consul-settings?logo=pypi&label=pydantic-consul-settings)](https://pypi.org/project/pydantic-consul-settings/)
[![PyPI publish](https://github.com/jag-k/pydantic-consul-settings/actions/workflows/build.yml/badge.svg)](https://github.com/jag-k/pydantic-consul-settings/actions/workflows/build.yml)

**Add Consul as source of env variable to settings**

This package provides a way to use [pydantic](https://docs.pydantic.dev/) settings with [consul](https://consul.io) as source of environment variables.


## Installation

```shell
pip install pydantic-consul-settings
```

## Usage

```python
from pydantic_settings import SettingsConfigDict
from pydantic_consul_settings import create_settings, ConsulBaseSettings


class ConsulSettings(ConsulBaseSettings):
    """Add additional settings for key generation"""

    stage: str = 'dev'
    service: str = 'my-service'


    @property
    def key_prefix(self) -> str:
        """Get the key prefix."""
        return f"{self.stage}/{self.service}"


BaseSettings = create_settings(ConsulSettings())


class Settings(BaseSettings):
    """App settings"""

    model_config = SettingsConfigDict(
      env_prefix='APP_',
    )

    # Get from env APP_NAME
    # and `dev/my-service/APP_NAME` from consul
    name: str = 'my-app'
    # Get from env APP_VERSION
    # and `dev/my-service/APP_VERSION` from consul
    version: str = '0.1.0'
    # Get from env APP_DESCRIPTION
    # and `dev/my-service/APP_DESCRIPTION` from consul
    description: str = 'My app description'


settings = Settings()

print(settings.dict())
```
