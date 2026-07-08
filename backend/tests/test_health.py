def test_health_reports_database_telegram_and_llm_details(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["db"] == "ok"
    assert payload["telegram"]["api_configured"] is True
    assert payload["telegram"]["sessions_dir"] == "ok"
    assert payload["llm"]["provider"] == "deepseek"
    assert payload["llm"]["model"] == "deepseek-v4-flash"
    assert payload["llm"]["configured"] is True
