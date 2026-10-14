"""Non-régression du schéma OpenAPI : la génération ne doit produire ni avertissement ni erreur."""
from django.core.management import call_command


def test_schema_openapi_sans_avertissement(tmp_path):
    """spectacular --validate --fail-on-warn échoue (SchemaGenerationError) au moindre avertissement."""
    fichier = tmp_path / "schema.yaml"
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(fichier))
    assert fichier.exists() and fichier.stat().st_size > 0
