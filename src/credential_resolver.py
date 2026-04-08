import os


def resolve_credential(vault_reference: str) -> str:
    """
    Takes a string like 'ENV.KYC_PROVIDER_KEY',
    strips the 'ENV.' prefix, and looks up the value in os.environ.
    """
    if not vault_reference.startswith("ENV."):
        raise ValueError(
            f"Invalid vault reference format: '{vault_reference}'. "
            f"Expected 'ENV.<VARIABLE_NAME>'."
        )

    env_var_name = vault_reference[4:]  # Strip 'ENV.'
    value = os.environ.get(env_var_name)

    if value is None:
        raise EnvironmentError(
            f"Credential not found: environment variable '{env_var_name}' is not set. "
            f"Add it to your .env file."
        )

    return value
