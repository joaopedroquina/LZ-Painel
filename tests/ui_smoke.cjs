// Browser-only demo tests: never call real Windows optimization commands.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://fonts.googleapis.com/**',r=>r.abort());
 await page.goto(pathToFileURL(path.resolve('index.html')).href);
 await page.waitForSelector('#splash.out');
 assert.equal(await page.locator('#demo').isVisible(),true);
 assert.equal(await page.locator('#winClose').isDisabled(),true);
 const categories=await page.locator('.side [data-v]').evaluateAll(es=>es.map(e=>e.dataset.v));
 assert.equal(categories.length,14);
 for(const k of categories){
  await page.evaluate(k=>go(k),k);
  assert.equal(await page.locator('#h1').innerText(),await page.evaluate(k=>T[k][0],k));
  assert.equal(await page.getByText('Não foi possível carregar esta tela.',{exact:false}).count(),0);
 }
 await page.evaluate(()=>go('jogos'));
 await page.locator('#gm').check();
 await page.waitForFunction(()=>document.querySelector('#fpsPlanStatus').textContent==='Alto desempenho ativado');
 await page.evaluate(()=>go('dash'));
 await page.evaluate(()=>go('jogos'));
 assert.equal(await page.locator('#gm').isChecked(),true);
 await page.locator('#gm').uncheck();
 await page.waitForFunction(()=>document.querySelector('#fpsPlanStatus').textContent==='Plano anterior restaurado');
 assert.equal(await page.locator('#fpsPlanName').innerText(),'Equilibrado');
 await page.locator('#fm').click();
 await page.waitForFunction(()=>document.querySelector('#fpsMemoryStatus').textContent.startsWith('Memória liberada:'));
 // Bridge calls use only these test doubles.
 await page.evaluate(()=>{
  window.testActions=[];
  window.pywebview={api:{window_action:async a=>{testActions.push(a);return true},window_state:async()=>({maximized:false})}};
  initWindowControls();
 });
 await page.locator('#winMin').click();
 await page.locator('#winMax').click();
 await page.locator('#appdrag').dblclick();
 await page.locator('#winClose').click();
 assert.deepEqual(await page.evaluate(()=>testActions),['minimize','maximize','maximize','close']);
 await page.evaluate(()=>window.setWindowMaximized(true));
 assert.equal(await page.locator('#winMax').getAttribute('aria-label'),'Restaurar janela');
 await page.evaluate(()=>{delete window.pywebview;});
 await page.evaluate(()=>Promise.all([go('monitor'),go('energia'),go('jogos')]));
 assert.equal(await page.locator('#h1').innerText(),'FPS Boost');
 assert.equal(await page.locator('.fps-hero').isVisible(),true);
 await page.emulateMedia({reducedMotion:'reduce'});
 assert.equal(await page.locator('.fps-card').first().evaluate(e=>getComputedStyle(e).animationName),'none');
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.evaluate(()=>document.body.classList.add('calm'));
 assert.equal(await page.locator('.fps-card').first().evaluate(e=>getComputedStyle(e).animationName),'none');
 await page.evaluate(()=>document.body.classList.remove('calm'));
 fs.mkdirSync('test-results',{recursive:true});
 await page.screenshot({path:'test-results/fps-boost.png',fullPage:true});
 await page.setViewportSize({width:1000,height:700});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:'test-results/fps-boost-1000.png',fullPage:true});
 await page.evaluate(()=>go('dash'));
 await page.waitForFunction(()=>!analyzing);
 await page.locator('#opt').click();
 await page.waitForFunction(()=>!quickBusy&&!document.querySelector('#quickResults').hidden,{},{timeout:30000});
 assert.equal(await page.locator('#quickClose').isEnabled(),true);
 await page.locator('#quickClose').click();
 assert.equal(await page.locator('#quickOverlay').isVisible(),false);
 assert.deepEqual(errors,[]);
 console.log('PASS: 13 categories, FPS actions/restoration, window bridge, rapid navigation, reduced motion, minimum width, optimize-all report.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
