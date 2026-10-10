import {decodeCrfAnswer,hasCrfAnswerMarker} from '../answerValues';
import {CrfMoreOptions} from './CrfMoreOptions';
import {Button,Form,Popconfirm,Space,Typography,theme} from 'antd';
import {crfMetadataFormName,crfRegistryFields,evaluateCrfCondition,readCrfPath} from '../fieldState';
import type {CrfName} from '../fieldState';
import {isCrfRecord} from '../formValues';
import type {RegistryField} from '../types';
import {CrfField} from './CrfField';

export function CrfRepeatTable({field,name,disabled}:{field:RegistryField;name:CrfName;disabled?:boolean}) {
 const form=Form.useFormInstance();const {token}=theme.useToken();const label=field.ui_label ?? field.label_zh;
 return <Form.Item noStyle shouldUpdate>{()=>{
  const all=form.getFieldsValue(true) as Record<string,unknown>;
  if(!evaluateCrfCondition(field.visible_when,all,crfRegistryFields))return null;
  // Never register descendants over a historical scalar container.
  for(let n=1;n<=name.length;n++){
   const value=readCrfPath(all,name.slice(0,n));
   if(value!=null && (n===name.length ? !Array.isArray(value)&&!hasCrfAnswerMarker(value) : (typeof value!=='object'||(Array.isArray(value)&&typeof name[n]!=='number')))) return <section aria-label={label}><Typography.Text type="warning">旧记录，待核对</Typography.Text><p style={{whiteSpace:'pre-wrap'}}>{typeof value==='string'?value:JSON.stringify(value)}</p></section>;
  }
  const metaName=crfMetadataFormName(field,name);const meta=metaName?readCrfPath(all,metaName):undefined;
  const rawAnswer=readCrfPath(all,name);const answer=decodeCrfAnswer(rawAnswer,meta);
  const listName=hasCrfAnswerMarker(rawAnswer)?[...name,'value']:name;
  const handled=answer.state==='unknown'||answer.state==='not_applicable';const inactive=disabled||handled;
  const children=field.children ?? [];const idKey=field.row_id_key ?? '_row_id';const metadataKey=field.row_metadata_key ?? '_field_meta';
  return <section id={name.join('_')} tabIndex={-1} aria-label={label} style={{containerType:'inline-size'}}>
   <style>{`.crf-repeat-grid {width:100%;border-collapse:collapse}.crf-repeat-grid td,.crf-repeat-grid th {padding:12px;vertical-align:top;text-align:left;border-bottom:1px solid ${token.colorBorderSecondary}} @container (max-width: 760px) {.crf-repeat-grid,.crf-repeat-grid tbody,.crf-repeat-grid tr,.crf-repeat-grid td {display:block;width:auto}.crf-repeat-grid thead {display:none}.crf-repeat-grid tr {margin-bottom:16px}.crf-repeat-grid td {border-bottom:0}}`}</style>
   <div className="crf-answer-label"><Typography.Title level={5}>{label}</Typography.Title><CrfMoreOptions field={field} answer={rawAnswer} legacyMeta={meta} disabled={disabled} onChange={value=>{
    if(handled&&!hasCrfAnswerMarker(value)&&metaName&&isCrfRecord(meta))form.setFields([{name:metaName,value:{...meta,state:null,reason:null},touched:true}]);
    form.setFields([{name,value,touched:true}]);
   }}/></div>
   <Form.List name={listName}>{(rows,{add,remove,move})=>(
    <>
     <div style={{overflowX:'auto'}}><table className="crf-repeat-grid"><thead><tr>{children.map(c=><th key={c.field_id} scope="col">{c.ui_label??c.label_zh}</th>)}<th scope="col">操作</th></tr></thead><tbody>
      {rows.map((row,index)=>{
       const rowName=[...listName,row.name];const raw=readCrfPath(form.getFieldsValue(true),rowName);
       return <tr key={row.key} role="group" aria-label={`${label}第${index+1}条`}>
        {isCrfRecord(raw)?children.map(c=><td key={c.field_id} style={{minWidth:180}}><CrfField field={c} name={[...rowName,...c.storage.split('.')]} registrationPrefix={listName} disabled={inactive}/></td>):<td colSpan={children.length}><Typography.Text type="warning">旧记录，待核对</Typography.Text><p>{typeof raw==='string'?raw:JSON.stringify(raw)}</p></td>}
        <td><Space wrap>
         <Button size="small" aria-label={`上移第${index+1}条`} disabled={inactive||index===0} onClick={()=>move(index,index-1)}>上移</Button>
         <Button size="small" aria-label={`下移第${index+1}条`} disabled={inactive||index===rows.length-1} onClick={()=>move(index,index+1)}>下移</Button>
         <Button size="small" aria-label={`清空第${index+1}条`} disabled={inactive||!isCrfRecord(raw)} onClick={()=>{
          if(!isCrfRecord(raw))return;
          // Explicit clearing does not replace the row or its identity.
          const cleared={...raw};children.forEach(c=>{const path=c.storage.split('.');let target=cleared;path.slice(0,-1).forEach(k=>{target[k]=isCrfRecord(target[k])?{...target[k]}:{};target=target[k] as Record<string,unknown>;});target[path[path.length-1]]=null;});
          const oldMeta=isCrfRecord(raw[metadataKey])?raw[metadataKey]:{};cleared[metadataKey]={...oldMeta,...Object.fromEntries(children.filter(c=>c.metadata).map(c=>[c.metadata!.key,{state:null,reason:null}]))};
          form.setFields([{name:rowName,value:cleared,touched:true}]);
         }}>清空</Button>
         <Popconfirm title={`确认删除${label}第${index+1}条？`} description="该条明细及反馈、原因将在保存后移除。" okText="确认删除" cancelText="取消" disabled={inactive} onConfirm={()=>{if(!inactive)remove(index);}}><Button danger size="small" aria-label={`删除第${index+1}条`} disabled={inactive}>删除</Button></Popconfirm>
        </Space></td>
       </tr>;
      })}
     </tbody></table></div>
     {rows.length===0?<Typography.Paragraph>暂无明细，可新增记录。</Typography.Paragraph>:null}
     <Button disabled={inactive} onClick={()=>add({[idKey]:crypto.randomUUID(),[metadataKey]:{}})}>新增{label}</Button>
    </>
   )}</Form.List>
  </section>;
 }}</Form.Item>;
}
