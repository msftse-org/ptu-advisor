import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();

page.on('console', (msg) => console.log('BROWSER:', msg.text()));
page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));

await page.route('**/api/**', async (route) => {
  const url = route.request().url();
  console.log('INTERCEPTED:', url);
  if (url.includes('/api/focus-topics')) {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ name: 'Cost Reduction', tagline: 'Tag' }]) });
    return;
  }
  if (url.includes('/api/pricing/options')) {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ regions: [{ name: 'eastus', display_name: 'East US', multiplier: 1.0 }], deployment_types: [{ name: 'Global', display_name: 'Global', rate_multiplier: 1.0 }] }) });
    return;
  }
  if (url.includes('/api/discovery/subscriptions')) {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    return;
  }
  if (url.includes('/api/analyze')) {
    const fullMock = {"recommendation":"ptu_recommended","confidence":0.93,"summary":"PTU is recommended based on strong workload signals.","explanation":"Your workload is stable and sees capacity pressure under PAYG.","what_would_change":"Lower sustained load and lower throttling would reduce PTU benefits.","data_quality":"Good data quality with sufficient lookback coverage.","analysis_period":"14 days","dimensions":[{"name":"Workload Shape","score":"positive","confidence":0.91,"summary":"Workload appears stable.","explanation":"Low variance and sustained throughput indicate PTU fit.","key_metrics":{"cv":0.42,"sustained":68.4},"is_positive":true}],"metrics":{"deployment_name":"demo-deployment","model_name":"gpt-4o","avg_tpm":12345,"peak_tpm":21456,"throttling_rate_pct":3.42,"total_requests":250000,"throttled_requests":8540,"successful_requests":241460,"total_tokens":99000000,"total_tokens_millions":99,"lookback_days":14,"latency":{"p50":420,"p95":910,"p99":1450},"utilization":{"peak_to_average_ratio":1.74,"sustained_utilization_rate":66,"active_hours_percentage":82,"business_hours_concentration":64,"weekend_vs_weekday_ratio":0.58}},"charts":{"tokens":{"timestamps":["2026-02-01T00:00:00Z","2026-02-01T00:15:00Z","2026-02-01T00:30:00Z","2026-02-01T00:45:00Z"],"prompt":[4000,4200,4150,4300],"completion":[2600,2800,2700,2900],"total":[6600,7000,6850,7200]},"requests":{"timestamps":["2026-02-01T00:00:00Z","2026-02-01T00:15:00Z","2026-02-01T00:30:00Z","2026-02-01T00:45:00Z"],"successful":[1000,1100,1080,1130],"throttled":[15,22,20,24],"total":[1015,1122,1100,1154]},"daily_cost":{"dates":["2026-02-01","2026-02-02"],"input_cost":[20.5,21.8],"output_cost":[52.0,56.0],"total_cost":[72.5,77.8],"avg_daily_cost":75.15,"ptu_daily_cost":173.33},"tpm":{"timestamps":["2026-02-01T00:00:00Z","2026-02-01T00:15:00Z","2026-02-01T00:30:00Z","2026-02-01T00:45:00Z"],"values":[12000,12800,12400,13000],"avg":12345,"p25":11200,"p95":21456},"throttling":{"timestamps":["2026-02-01T00:00:00Z","2026-02-01T00:15:00Z","2026-02-01T00:30:00Z","2026-02-01T00:45:00Z"],"values":[15,22,20,24]},"cost_curves":{"baseline_tpm":[5000,10000],"payg_monthly":[1800,3600],"ptu_spill_monthly":[1700,2900],"ptu_units":[15,20],"break_even_tpm":8200,"slider_baseline_tpm":10000,"payg_at_slider":3600,"hybrid_at_slider":2900}},"cost_analysis":{"pricing":{"focus_topic":"Cost Reduction","reservation_type":"Monthly Commitment (Estimated 64% off)","reservation_discount_pct":64,"payg_blended_rate_per_million":4.75,"ptu_hourly_rate":1,"ptu_capacity_per_unit":2500},"payg":{"monthly_tokens":99000000,"payg_base":470,"throttle_impact":120,"payg_total":590},"hybrid":{"baseline_percentile":75,"baseline_label":"P75","baseline_tpm":10000,"baseline_ptu":20,"ptu_capacity_tpm":50000,"avg_spillover_tpm":800,"spillover_tokens_monthly":34560000,"spillover_cost":164,"ptu_baseline_cost":5200,"hybrid_total":5364,"spillover_pct":22},"full_ptu":{"ptu_needed_full":25,"ptu_monthly_full":18000,"ptu_committed_cost":6500},"comparison":{"savings":740,"savings_pct":12.1,"break_even_tpm":8200,"cheaper_strategy":"PTU + Spillover"},"formula_blocks":{"payg":"payg formula block","hybrid":"hybrid formula block"}},"insights":{"break_even_message":"Your average usage is above break-even.","focus_topic":"Cost Reduction","analysis_notes":["Note 1","Note 2"]}};
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fullMock) });
    return;
  }
  await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
});

await page.goto('http://127.0.0.1:4173');
await page.waitForTimeout(2000);

const demoBtn = page.getByRole('button', { name: 'Demo Mode' });
console.log('Demo button visible:', await demoBtn.isVisible());
if (await demoBtn.isVisible()) {
  await demoBtn.click();
  await page.waitForTimeout(1000);
}

const runBtn = page.getByRole('button', { name: 'Run Analysis' });
console.log('Run Analysis visible:', await runBtn.isVisible());
if (await runBtn.isVisible()) {
  await runBtn.click();
  await page.waitForTimeout(3000);
}

await page.screenshot({ path: 'tests/screenshots/debug-tooltip.png', fullPage: true });
const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 3000));
console.log('PAGE TEXT:\n', bodyText);
await browser.close();
