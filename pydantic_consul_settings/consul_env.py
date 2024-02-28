import logging

from typing import Any, Dict, Literal, Tuple, Type, TypedDict

from consul import Consul, ConsulException
from pydantic.fields import Field, FieldInfo
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import PydanticBaseSettingsSource
from pydantic_settings import SettingsConfigDict as PydanticSettingsConfigDict


__all__ = (
    "BaseSettingsWithConsul",
    "ConsulClientSettings",
    "SettingsConfigDict",
)

logger = logging.getLogger("pydantic_consul_settings")


class ConsulValue(TypedDict, total=False):
    """Consul value."""

    LockIndex: int  # 0
    Key: str  # "service/LOG_FORMAT"
    Flags: int  # 0
    Value: bytes  # b"INFO"
    CreateIndex: int  # 1234
    ModifyIndex: int  # 1234


class ConsulClientSettings(PydanticBaseSettings):
    """Consul settings."""

    model_config = PydanticSettingsConfigDict(
        title="Consul Settings",
        env_prefix="CONSUL_",
    )

    host: str = Field(..., description="The host of the Consul.")
    port: int = Field(8501, description="The port of the Consul.")
    token: str | None = Field(
        None,
        description="The token for the Consul. Must be set to use Consul as env source.",
    )
    scheme: str = Field(
        "http",
        description="The scheme of the Consul.",
    )
    consistency: Literal["default", "consistent", "stale"] = Field(
        "default",
        description="The consistency of the Consul.",
    )
    dc: str | None = Field(None, description="The datacenter of the Consul.")
    verify: bool = Field(True, description="Verify the SSL certificate.")
    cert: str | None = Field(None, description="The client side certificates for HTTPS requests.")

    def client(self) -> Consul:
        """Get the Consul client."""
        return Consul(
            host=self.host,
            port=self.port,
            token=self.token,
            scheme=self.scheme,
            consistency=self.consistency,
            dc=self.dc,
            verify=self.verify,
            cert=self.cert,
        )

    @property
    def key_prefix(self) -> str:
        """Get the key prefix.

        Can be overridden in the child classes to set the key prefix.
        :return: The key prefix.
        """
        return ""

    def enabled(self) -> bool:
        """Check if Consul is enabled.

        Check if the host and the port are set and if the Consul status leader is available.

        :return: True if Consul is enabled, False otherwise
        """
        if not all([self.host, self.port]):
            logger.debug("Consul is not enabled. The host and the port are not set.")
            return False

        try:
            self.client().status.leader()
            return True
        except ConsulException as e:
            logger.debug("Consul is not enabled. Failed to get the leader.", exc_info=e)
            return False


class ConsulConfigSettingsSource(PydanticBaseSettingsSource):
    """Consul settings source.

    This source loads the settings values from the Consul.
    """

    def __init__(
        self,
        settings_cls: Type[PydanticBaseSettings],
        consul_settings: ConsulClientSettings,
    ) -> None:
        super().__init__(settings_cls)
        self.consul = consul_settings.client()
        self.consul_prefix = consul_settings.key_prefix
        self.prefix = settings_cls.model_config.get("env_prefix", "")

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[ConsulValue | None, str, bool]:
        """Gets the value, the key for model creation, and a flag to determine whether value is complex.

        This is an abstract method that should be overridden in every settings source classes.

        :param field: The field.
        :param field_name: The field name.
        :return: A tuple contains the key, value and a flag to determine whether value is complex.
        """
        try:
            index, values = self.consul.kv.get(
                f"{self.consul_prefix}/{self.prefix}{(field.alias or field_name).upper()}",
            )  # type: str, ConsulValue | None
            logger.debug("Got the value for the field %r from the Consul with index %s: %r", field_name, index, values)
            return values, field_name, True

        except ConsulException as e:
            logger.debug(
                "Failed to get the value for the field %r from the Consul.",
                field_name,
                exc_info=e,
            )
            return None, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        field_value: ConsulValue | None,
        value_is_complex: bool,
    ) -> str | None:
        """Prepare the field value.

        This is an abstract method that should be overridden in every settings source classes.

        :param field_name: The field name.
        :param field: The field.
        :param field_value: The field value.
        :param value_is_complex: The flag to determine whether value is complex.
        :return: The prepared field value.
        """
        if isinstance(field_value, dict):
            raw_value = field_value.get("Value", None)
            if isinstance(raw_value, bytes):
                return raw_value.decode()
        return None

    def __call__(self) -> Dict[str, Any]:
        """Load the settings values from the Consul and return them as a dictionary."""
        d: Dict[str, Any] = {}

        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(field, field_name)
            field_value = self.prepare_field_value(field_name, field, field_value, value_is_complex)
            if field_value is not None:
                d[field_key] = field_value

        return d


class SettingsConfigDict(PydanticSettingsConfigDict, total=False):
    """Consul settings config dict."""

    consul_model: ConsulClientSettings | None


class BaseSettingsWithConsul(PydanticBaseSettings):
    """New base settings settings."""

    model_config: SettingsConfigDict

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[PydanticBaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Define the sources and their order for loading the settings values.

        :param settings_cls: The Settings class.
        :param init_settings: The `InitSettingsSource` instance.
        :param env_settings: The `EnvSettingsSource` instance.
        :param dotenv_settings: The `DotEnvSettingsSource` instance.
        :param file_secret_settings: The `SecretsSettingsSource` instance.
        :return: A tuple containing the sources and their order for loading the settings values.
        """
        settings_source = super().settings_customise_sources(
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )
        consul_settings: ConsulClientSettings | None = cls.model_config.get("consul_model", None)
        if not isinstance(consul_settings, ConsulClientSettings):
            logger.debug("Consul settings are not set or not valid. Skip Consul settings source.")
            return settings_source
        if not consul_settings.enabled():
            logger.debug("Consul is not enabled. Skip Consul settings source.")
            return settings_source
        logger.debug("Add Consul settings source.")
        return (
            settings_source[0],
            ConsulConfigSettingsSource(settings_cls, consul_settings=consul_settings),
            *settings_source[1:],
        )
