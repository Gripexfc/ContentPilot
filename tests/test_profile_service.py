from creatoros.domain.profile import ProfileSnapshot, ProfileVersionCreate
from creatoros.services.profile_service import create_version, diff_versions, restore_version


def snapshot(name: str, pillar: str) -> ProfileSnapshot:
    return ProfileSnapshot(
        identity={"display_name": name, "profession": "产品架构师"},
        pillars=[pillar],
        platforms={"wechat": {"positioning": "解释复杂问题"}},
    )


def test_profile_versions_and_restore(app_settings):
    from creatoros.db.session import build_engine, session_factory
    from creatoros.db.migrations import run_migrations

    engine = build_engine(app_settings)
    run_migrations(app_settings)
    session = session_factory(engine)()
    first = create_version(session, ProfileVersionCreate(snapshot=snapshot("一号作者", "工程实践")))
    second = create_version(
        session,
        ProfileVersionCreate(
            snapshot=snapshot("一号作者", "内容系统"),
            base_version_id=first.id,
            change_summary="调整内容支柱",
        ),
    )
    changes = diff_versions(session, first.id, second.id)
    assert any(item["path"] == "pillars" for item in changes)
    restored = restore_version(session, first.id)
    assert restored.version_no == 3
    assert restored.parent_version_id == second.id
    session.close()
    engine.dispose()


def test_stale_profile_update_is_rejected(app_settings):
    from creatoros.db.session import build_engine, session_factory
    from creatoros.db.migrations import run_migrations
    from creatoros.services.profile_service import ProfileConflict

    engine = build_engine(app_settings)
    run_migrations(app_settings)
    session = session_factory(engine)()
    first = create_version(session, ProfileVersionCreate(snapshot=snapshot("作者", "A")))
    create_version(session, ProfileVersionCreate(snapshot=snapshot("作者", "B"), base_version_id=first.id))
    try:
        create_version(session, ProfileVersionCreate(snapshot=snapshot("作者", "C"), base_version_id=first.id))
    except ProfileConflict:
        pass
    else:
        raise AssertionError("过期画像版本应该被拒绝")
    finally:
        session.close()
        engine.dispose()


def test_migrations_are_idempotent(app_settings):
    import sqlite3

    from creatoros.db.migrations import run_migrations
    from creatoros.db.session import build_engine

    engine = build_engine(app_settings)
    run_migrations(app_settings)
    run_migrations(app_settings)
    connection = sqlite3.connect(app_settings.database_path)
    assert connection.execute("select version_num from alembic_version").fetchone() == ("0009_quick_draft_persistence",)
    connection.close()
    engine.dispose()
