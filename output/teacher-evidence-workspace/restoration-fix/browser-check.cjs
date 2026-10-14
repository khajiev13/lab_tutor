const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const TARGET_URL = process.env.TARGET_URL || 'http://127.0.0.1:18766';
const OUT = process.env.RESTORATION_OUTPUT || '/tmp/labtutor-restoration-browser';
const candidate = {candidate_id:'sql',display_name:'SQL',category_id:'tools',original_labels:['SQL'],aliases:[],evidence_references:[],job_metrics:{supporting_posting_count:2,assessed_posting_count:2,selected_posting_count:2,percentage:100,coverage_status:'complete'},onet_associations:[],recommendation_reasons:[],posting_support:'supported',qualifying_posting_links:['https://example.org/jobs/1']};
const state = {course_id:2,course_title:'Restoration test course',course_description:'Synthetic browser fixture',run_id:'restore-test-run',job_search_country:'USA',job_search_country_confirmed:true,job_search_location:'United States',fetched_jobs:null,job_groups:null,selected_jobs:null,extracted_skills:null,total_jobs_for_extraction:null,existing_graph_skills:null,existing_concepts:null,curriculum_mapping:null,selected_for_insertion:null,skill_concepts:null,insertion_results:null,skill_job_urls:null};
const review = {run_id:'restore-test-run',candidate_revision:1,selection_revision:2,publication_revision:0,categories:[{category_id:'tools',label:'Tools'}],candidates:[candidate],selected_candidate_ids:['sql'],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,approved_references:[],reconciliations:[]};
const history = {messages:[{id:'saved-1',role:'agent',agent:'market_analyst',agentDisplayName:'Market analyst',agentEmoji:'',content:'Your saved conversation is restored.',toolCalls:[],isStreaming:false}],threadId:'synthetic-restore-thread'};
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});
 const browser=await chromium.launch({channel:"chrome",headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 const page=await context.newPage();
 const errors=[];const unexpected=[];const writes=[];const counts={};let pendingHistory=true;let firstHistoryTime=null;
 page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(()=>localStorage.setItem('access_token','fixture.'+btoa(JSON.stringify({exp:4102444800}))+'.not-a-real-signature'));
 await page.route('**/*',async route=>{
  const request=route.request();const url=new URL(request.url());
  if(!['fetch','xhr'].includes(request.resourceType())){
   if(url.origin!==new URL(TARGET_URL).origin) return route.abort();
   return route.continue();
  }
  const endpoint=url.pathname;counts[endpoint]=(counts[endpoint]||0)+1;
  if(request.method()!=='GET'){writes.push(request.method()+' '+endpoint);return route.abort();}
  const reply=data=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
  if(endpoint==='/users/me')return reply({id:1,first_name:'Test',last_name:'Teacher',email:'teacher@example.test',role:'teacher',created_at:'2026-01-01'});
  if(endpoint==='/courses/2')return reply({id:2,title:'Restoration test course',description:'Synthetic browser fixture',teacher_id:1,created_at:'2026-01-01',extraction_status:'not_started',publication_status:'draft',market_gate_status:'not_started',level:'bachelor'});
  if(endpoint.endsWith('/market-demand/history')){
   if(pendingHistory){firstHistoryTime??=Date.now();return;}
   return reply(history);
  }
  if(endpoint.endsWith('/market-demand/state'))return reply(state);
  if(endpoint.endsWith('/market-demand/skill-review'))return reply(review);
  if(endpoint.endsWith('/market-demand/execution-status'))return reply({status:'idle',state_updated_at:'2026-10-14T10:00:00Z'});
  if(endpoint.endsWith('/market-demand/sources'))return reply([{id:'headhunter',label:'HeadHunter',availability:'available',reason:null}]);
  if(endpoint.endsWith('/occupation-reference/releases'))return reply({items:[]});
  if(endpoint.endsWith('/occupation-reference/occupations'))return reply({items:[],total:0,release:'31.0'});
  if(endpoint.endsWith('/embedding-status'))return reply({course_id:2,extraction_status:'not_started',embedding_status:'not_started',files:[]});
  if(endpoint.endsWith('/files'))return reply([]);
  unexpected.push(endpoint);return route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Synthetic fixture: no result"}'});
 });
 try{
  await page.goto(TARGET_URL+'/courses/2/market-analyst');
  await page.getByText('Restoring conversation...', {exact:true}).waitFor({state:'visible'});
  await page.screenshot({path:path.join(OUT,'loading.png')});
  await page.getByRole('button',{name:'Retry restoration',exact:true}).waitFor({state:'visible',timeout:35000});
  const timeoutElapsedMs=Date.now()-firstHistoryTime;
  if(timeoutElapsedMs<29000||timeoutElapsedMs>34000)throw new Error('Unexpected restoration deadline: '+timeoutElapsedMs);
  if(await page.getByText('Restoring conversation...', {exact:true}).count())throw new Error('Spinner persisted after deadline');
  await page.screenshot({path:path.join(OUT,'timeout.png')});
  const beforeRetry=counts['/courses/2/market-demand/history'];
  if(beforeRetry!==1)throw new Error('Unexpected automatic retry: '+beforeRetry);
  pendingHistory=false;
  await page.getByRole('button',{name:'Retry restoration',exact:true}).click();
  await page.getByText('Your saved conversation is restored.',{exact:true}).waitFor({state:'visible'});
  await page.getByText('1 chosen · 1 job-backed skills', {exact:true}).waitFor({state:'visible'});
  if(await page.getByRole('button',{name:'Retry restoration',exact:true}).count())throw new Error('Error did not clear');
  if(await page.getByText('Restoring conversation...', {exact:true}).count())throw new Error('Restoration spinner did not clear');
  if(writes.length)throw new Error('Unexpected write: '+writes.join(', '));
  if(errors.length)throw new Error('Browser errors: '+errors.join(', '));
  await page.screenshot({path:path.join(OUT,'restored.png')});
  const result={passed:true,fixture:'Synthetic HTTP responses; built real frontend; no production credentials or requests',timeoutElapsedMs,manualRetryRestoresTranscript:true,savedSelectionRestored:true,automaticRetries:0,writes:0,pageErrors:errors,unrelatedUnavailableReads:[...new Set(unexpected)],requests:counts};
  fs.writeFileSync(path.join(OUT,'browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }catch(error){await page.screenshot({path:path.join(OUT,'failure.png')});fs.writeFileSync(path.join(OUT,'failure.json'),JSON.stringify({message:error.message,errors,unexpected,writes,counts},null,2));throw error;}
 finally{await browser.close();}
})();
