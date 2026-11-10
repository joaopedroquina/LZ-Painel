// Smoke test para o FPS Boost atual; sem comandos reais de otimização.
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
  assert.equal(new Set(categories).size,14);
  for(const k of categories){
   await page.evaluate(k=>go(k),k);
   assert.equal(await page.locator('#h1').innerText(),await page.evaluate(k=>T[k][0],k));
   assert.equal(await page.getByText('Não foi possível carregar esta tela.',{exact:false}).count(),0,'Falha na categoria '+k);
  }
  await page.evaluate(()=>go('jogos'));
  assert.equal(await page.locator('.fpsx-page').isVisible(),true);
  assert.equal(await page.locator('.fpsx-cat').count(),8);
  assert.equal(await page.locator('.fpsx-item').count(),10);
  assert.equal(await page.locator('#fpsPaneTitle').innerText(),'Privacidade e Telemetria');
  assert.equal(await page.locator('[data-privacy]').count(),0); // Navegador de prévia: ajustes reais indisponíveis.
  await page.locator('[data-fpscat="games"]').click();
  assert.equal(await page.locator('#fpsPaneTitle').innerText(),'Jogos');
  assert.equal(await page.locator('.fpsx-item').count(),4);
  await page.locator('[data-fpscat="interface"]').click();
  assert.equal(await page.locator('#fpsPaneTitle').innerText(),'Desempenho e Interface');
  assert.equal(await page.locator('.fpsx-item').count(),5);
  await page.locator('[data-fpscat="services"]').click();
  assert.equal(await page.locator('#fpsPaneTitle').innerText(),'Serviços');
  assert.equal(await page.locator('.fpsx-item').count(),4);
  await page.evaluate(()=>go('game'));
  assert.equal(await page.locator('.gb-card').count(),5);
  assert.equal(await page.locator('.gb-main-action').count(),5);
  assert.equal(await page.locator('.gb-main-action:disabled').count(),5);
  assert.equal(await page.locator('.gb-state').count(),5);

  await page.locator('[data-gbtab="advanced"]').click();
  assert.equal(await page.locator('.gb-advanced button').count(),4);
  await page.locator('[data-gbtab="history"]').click();
  assert.equal(await page.locator('.gb-history').count(),1);
  await page.evaluate(()=>go('jogos'));

  await page.evaluate(()=>{
   window.testActions=[];
   window.pywebview={api:{window_action:async action=>{window.testActions.push(action);return true}}};
   bindWindowChrome();
  });
  assert.equal(await page.locator('#winClose').isEnabled(),true);
  await page.locator('#winMin').click();
  await page.locator('#winMax').click();
  await page.locator('#appdrag').dblclick();
  await page.locator('#winClose').click();
  assert.deepEqual(await page.evaluate(()=>window.testActions),['minimize','maximize','maximize','close']);
  await page.evaluate(()=>window.setWindowMaximized(true));
  assert.equal(await page.locator('#winMax').getAttribute('aria-label'),'Restaurar janela');
  await page.evaluate(()=>{delete window.pywebview;bindWindowChrome()});
  assert.equal(await page.locator('#winClose').isDisabled(),true);
  await page.evaluate(()=>Promise.all([go('mem'),go('rede'),go('jogos')]));
  assert.equal(await page.locator('#h1').innerText(),'FPS Boost');
  assert.equal(await page.locator('.fpsx-page').isVisible(),true);
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.evaluate(()=>motionOn()),false);
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{S.calm=true;document.body.classList.add('calm')});
  assert.equal(await page.evaluate(()=>motionOn()),false);
  await page.evaluate(()=>{S.calm=false;document.body.classList.remove('calm')});
  fs.mkdirSync('test-results',{recursive:true});
  await page.screenshot({path:'test-results/fps-boost.png',fullPage:true});
  await page.setViewportSize({width:1000,height:700});
  await page.screenshot({path:'test-results/fps-boost-1000.png',fullPage:true});
  await page.evaluate(()=>go('dash'));
  await page.waitForFunction(()=>!analyzing);
  await page.locator('#opt').click();
  await page.waitForFunction(()=>!quickBusy&&!document.querySelector('#quickResults').hidden,{},{timeout:30000});
  assert.equal(await page.locator('#quickClose').isEnabled(),true);
  await page.locator('#quickClose').click();
  assert.equal(await page.locator('#quickOverlay').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: 14 categorias, FPS Boost, barra da janela, navegação e otimizar tudo.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
