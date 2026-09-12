const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { planificar, validarResultado, prepararCarpeta, consolidarCarpeta, finalizarCaso } = require('./investigacion_identidad');
const paquete = () => ({version:1, job_id:'abcdef123456', huella_contexto:'a'.repeat(64), tipo_evaluacion:'obras', omitidos:[], casos:[{caso_id:'1:1',n_prof:1,n_exp:1,subobra:null,declarado:{cui:null},contexto_backend:{cui:'1234567',obra:{obra_id:42}},accion:'comprobar_fichas',disparadores:[]}]});
const listado = candidatos => ({'1234567':{ok:true,estado:'disponible',cui_consultado:'1234567',candidatos}});
const respuesta = () => ({version:1,job_id:'abcdef123456',huella_contexto:'a'.repeat(64),caso_id:'1:1',estado:'sin_candidato',seleccion_propuesta:null,candidatos:[],evidencias:[],consultas:[{fuente:'MEF',consulta:'Proyecto',estado:'sin_resultados',detalle:'Sin coincidencias en esta consulta'}],discrepancias:[],faltantes:['Identidad'],motivo:'No hallado en la consulta realizada',limites:['No demuestra inexistencia']});
test('ficha única coincidente no equivale a identidad verificada', () => {
  const p=paquete(), previo=JSON.stringify(p);
  const plan=planificar(p,listado([{obra_id:42}]));
  assert.equal(plan.tareas.length,0);
  assert.equal(plan.sin_alerta_en_listado[0].listado_completo_verificado,false);
  assert.equal(JSON.stringify(p),previo);
});
test('varias fichas, ficha diferente, fallo y listado mal formado se investigan', () => {
  for(const l of [{},listado([{obra_id:42},{obra_id:43}]),listado([{obra_id:43}]),listado([null])])
    assert.equal(planificar(paquete(),l).tareas.length,1);
});
test('señal explícita nunca se oculta por listado único', () => {
  const p=paquete();p.casos[0].accion='investigar';p.casos[0].disparadores=['consulta_no_completada'];
  assert.equal(planificar(p,listado([{obra_id:42}])).tareas.length,1);
});
test('rechaza respuestas de otro contexto, caso, job y campos de aplicación', () => {
  for(const cambio of [{job_id:'111111111111'},{caso_id:'2:1'},{huella_contexto:'b'.repeat(64)},{aplicar:true}])
    assert.throws(()=>validarResultado({...respuesta(),...cambio},paquete(),'1:1'));
  assert.equal(validarResultado(respuesta(),paquete(),'1:1').estado,'sin_candidato');
});
test('asociación requiere evidencia leída para identificadores y faltantes explícitos', () => {
  const r=respuesta();r.estado='asociacion_propuesta';r.seleccion_propuesta={candidato_id:'a',motivo:'Identidad citada'};
  r.candidatos=[{id:'a',cui:'1234567',obra_id:null,intervencion:'Obra principal',procedimiento:null,evidencias:['c','i'],motivo:'Coinciden documentos'}];
  r.evidencias=['cui','intervencion'].map((campo,i)=>({id:i?'i':'c',campo,fuente:'Registro oficial',tipo_fuente:'oficial',url:'https://example.gob.pe/proyecto',ubicacion:'Página 1',pagina_pdf:1,cita:'Texto literal de prueba',acceso:'leido'}));
  assert.equal(validarResultado(r,paquete(),'1:1').estado,'asociacion_propuesta');
  const declarada=structuredClone(r);declarada.evidencias[0].tipo_fuente='propuesta';
  assert.throws(()=>validarResultado(declarada,paquete(),'1:1'),/oficial/);
  const copia=structuredClone(r);copia.evidencias[0].acceso='no_leido';
  assert.throws(()=>validarResultado(copia,paquete(),'1:1'));
  r.faltantes=[];assert.throws(()=>validarResultado(r,paquete(),'1:1'));
});

test('RUC y contrato seleccionado se auditan incluso con ficha única y paquete antiguo',()=>{
  for(const cambio of [{via:'RUC'},{seace:{estado:'seleccionado'}}]) {
    const p=paquete();Object.assign(p.casos[0].contexto_backend,cambio);
    const plan=planificar(p,listado([{obra_id:42}]));
    assert.equal(plan.tareas.length,1);assert.equal(plan.sin_alerta_en_listado.length,0);
  }
  const p=paquete();p.casos[0].disparadores=['riesgo_documental'];
  assert.equal(planificar(p,listado([{obra_id:42}])).tareas.length,1);
});

test('finalizador agrega metadatos sin reparaciones silenciosas ni sobreescritura',t=>{
  const raiz=fs.mkdtempSync(path.join(os.tmpdir(),'identidad-finalizar-'));
  t.after(()=>fs.rmSync(raiz,{recursive:true,force:true}));
  const carpeta=path.join(raiz,'lote');prepararCarpeta(paquete(),{},carpeta);
  const r=respuesta();for(const k of ['version','job_id','huella_contexto','caso_id'])delete r[k];
  const archivo=path.join(carpeta,'P1_E1','borrador.json');
  fs.writeFileSync(archivo,JSON.stringify({...r,huella_contexto:'b'.repeat(64)}));
  assert.throws(()=>finalizarCaso(carpeta,'1:1'),/contradictorio/);
  assert.equal(fs.existsSync(path.join(carpeta,'P1_E1','resultado.json')),false);
  fs.writeFileSync(archivo,JSON.stringify({...r,aplicar:true}));
  assert.throws(()=>finalizarCaso(carpeta,'1:1'));
  fs.writeFileSync(archivo,JSON.stringify(r));
  assert.throws(()=>finalizarCaso(carpeta,'../otro'),/ajeno/);
  assert.equal(finalizarCaso(carpeta,'1:1').huella_contexto,'a'.repeat(64));
  assert.deepEqual(JSON.parse(fs.readFileSync(archivo,'utf8')),r);
  assert.throws(()=>finalizarCaso(carpeta,'1:1'));
  assert.equal(consolidarCarpeta(carpeta).aplicado_al_job,false);
});
test('privada sin evidencia del proyecto se rechaza',()=>{
  assert.throws(()=>validarResultado({...respuesta(),estado:'no_aplica_publica'},paquete(),'1:1'));
});

test('privadas y documentos no desaparecen por ficha única',()=>{
  for (const extra of [{via:'PRIVADA'}, {documentos_prioritarios:[{referencia:'a'.repeat(64)}]}]) {
    const p=paquete(); Object.assign(p.casos[0].contexto_backend,extra);
    assert.equal(planificar(p,listado([{obra_id:42}])).tareas.length,1);
  }
});

test('cada documento exige acceso registrado; leído no es enlace hallado',()=>{
  const p=paquete(), r=respuesta(), referencia='a'.repeat(64), url='https://estado.test/contrato.pdf';
  p.casos[0].contexto_backend.documentos_prioritarios=[{referencia,url}];
  assert.throws(()=>validarResultado(r,p,'1:1'),/documento prioritario/);
  r.consultas.push({fuente:'SEACE',consulta:`documento:${referencia}`,estado:'no_consultado',detalle:'Archivo no accesible en esta prueba'});
  assert.equal(validarResultado(r,p,'1:1').estado,'sin_candidato');
  r.consultas[1].estado='leido';
  assert.throws(()=>validarResultado(r,p,'1:1'),/página física/);
  r.evidencias=[{id:'doc',campo:'contrato',fuente:'SEACE',tipo_fuente:'oficial',url,ubicacion:'Documento, página física 1',pagina_pdf:1,cita:'Contrato con la entidad',acceso:'leido'}];
  assert.equal(validarResultado(r,p,'1:1').estado,'sin_candidato');
  r.evidencias[0].url='https://estado.test/otro.pdf';
  assert.throws(()=>validarResultado(r,p,'1:1'),/página física/);
});

test('lote con todas las respuestas puede conservar documentos pendientes',t=>{
  const raiz=fs.mkdtempSync(path.join(os.tmpdir(),'documentos-test-'));
  t.after(()=>fs.rmSync(raiz,{recursive:true,force:true}));
  const p=paquete(), r=respuesta(), referencia='a'.repeat(64);
  p.casos[0].contexto_backend.documentos_prioritarios=[{referencia,url:'https://estado.test/acto.pdf'}];
  r.consultas.push({fuente:'MEF',consulta:`documento:${referencia}`,estado:'no_consultado',detalle:'Sin copia disponible'});
  const carpeta=path.join(raiz,'lote'); prepararCarpeta(p,{},carpeta);
  fs.writeFileSync(path.join(carpeta,'P1_E1','resultado.json'),JSON.stringify(r));
  const salida=consolidarCarpeta(carpeta);
  assert.equal(salida.cobertura,'completa');
  assert.equal(salida.pendientes_documentales.length,1);
  assert.equal(salida.pendientes_documentales[0].motivo,'Sin copia disponible');
  assert.equal(salida.aplicado_al_job,false);
});
test('lote parcial reanudable y sin escritura sobre el job', t => {
  const raiz=fs.mkdtempSync(path.join(os.tmpdir(),'identidad-test-'));
  t.after(()=>fs.rmSync(raiz,{recursive:true,force:true}));
  const carpeta=path.join(raiz,'lote');
  prepararCarpeta(paquete(),{},carpeta);
  assert.throws(()=>prepararCarpeta(paquete(),{},carpeta));
  assert.equal(consolidarCarpeta(carpeta).cobertura,'parcial');
  fs.writeFileSync(path.join(carpeta,'P1_E1','resultado.json'),JSON.stringify(respuesta()));
  const salida=consolidarCarpeta(carpeta);
  assert.equal(salida.cobertura,'completa');assert.equal(salida.aplicado_al_job,false);
});
