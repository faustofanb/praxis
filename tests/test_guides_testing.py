from __future__ import annotations

from pathlib import Path

from praxis.guides.testing import maven_test_hint


def _maven_repo(root: Path, properties: dict[str, str]) -> Path:
    repo = root / "ifc-mom-column-max"
    (repo / "lamp-dependencies-parent").mkdir(parents=True)
    props = "".join(
        f"<{key}>{value}</{key}>" for key, value in properties.items()
    )
    (repo / "lamp-dependencies-parent" / "pom.xml").write_text(
        "<project>\n"
        "  <properties>\n"
        f"    {props}\n"
        "  </properties>\n"
        "</project>\n",
        encoding="utf-8",
    )
    return repo


def test_maven_skip_properties_produce_override_command(tmp_path: Path) -> None:
    repo = _maven_repo(
        tmp_path,
        {
            "ifc.surefire.skipTests": "true",
            "ifc.surefire.skip": "true",
        },
    )

    result = maven_test_hint(repo, module="ifc-mom-column-max")

    assert result.ok
    command = result.data["command"]
    assert "-Difc.surefire.skipTests=false" in command
    assert "-Difc.surefire.skip=false" in command
    assert "-pl ifc-mom-column-max" in command
    assert result.data["skipped_by_default"] == [
        "ifc.surefire.skipTests",
        "ifc.surefire.skip",
    ]


def test_maven_without_skip_returns_plain_command(tmp_path: Path) -> None:
    repo = _maven_repo(tmp_path, {"maven.compiler.source": "17"})

    result = maven_test_hint(repo, module="mes-pda")

    assert result.ok
    assert result.data["command"] == "mvn test -pl mes-pda"
    assert result.data["skipped_by_default"] == []


def test_maven_hint_without_module_omits_pl(tmp_path: Path) -> None:
    repo = _maven_repo(tmp_path, {"maven.test.skip": "true"})

    result = maven_test_hint(repo)

    assert result.ok
    assert result.data["command"] == "mvn test -Dmaven.test.skip=false"
    assert result.data["skipped_by_default"] == ["maven.test.skip"]


def test_maven_hint_requires_existing_repository(tmp_path: Path) -> None:
    result = maven_test_hint(tmp_path / "missing")

    assert not result.ok
    assert result.code == "TEST_HINT_REPOSITORY_NOT_FOUND"


_HARDCODED_SUREFIRE_POM = """<project>
  <build>
    <pluginManagement>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-surefire-plugin</artifactId>
          <configuration>
            <skipTests>true</skipTests>
            <skip>true</skip>
          </configuration>
        </plugin>
      </plugins>
    </pluginManagement>
  </build>
</project>
"""


def test_maven_hardcoded_surefire_skip_reported_as_unoverridable(tmp_path: Path) -> None:
    repo = tmp_path / "ifc-mom-column-max"
    (repo / "lamp-dependencies-parent").mkdir(parents=True)
    (repo / "lamp-dependencies-parent" / "pom.xml").write_text(
        _HARDCODED_SUREFIRE_POM, encoding="utf-8"
    )

    result = maven_test_hint(repo, module="lamp-mes-bff/lamp-mes-bff-server")

    assert result.ok
    assert result.data["skipped_by_default"] == []
    hardcoded = result.data["hardcoded_skips"]
    assert "lamp-dependencies-parent/pom.xml#skipTests" in hardcoded
    assert "lamp-dependencies-parent/pom.xml#skip" in hardcoded
    note = result.data["note"]
    assert "无法覆盖" in note and "${" in note
    assert "=false" not in result.data["command"]
