import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form, Input } from 'antd';
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { useCrfDraft } from './useCrfDraft';
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function Editor() { const [form] = Form.useForm(); const draft = useCrfDraft({ form, serverValues: { note: 'old' }, recordKey: '1' }); return <Form form={form}>{draft.navigationGuard}<Form.Item name="note"><Input aria-label="note"/></Form.Item><Link to="/other">离开</Link></Form>; }
it('guards actual link and history back with leave/stay decisions', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const router = createMemoryRouter([{ path: '/edit', element: <Editor /> }, { path: '/other', element: <div>其他页面</div> }], { initialEntries: ['/other', '/edit'], initialIndex: 1 });
    render(<RouterProvider router={router}/>);
    fireEvent.change(await screen.findByLabelText('note'), { target: { value: 'draft' } });
    fireEvent.click(screen.getByText('离开'));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('note')).toHaveValue('draft');
    await act(async () => { await router.navigate(-1); });
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(2));
    expect(router.state.location.pathname).toBe('/edit');
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByText('离开'));
    expect(await screen.findByText('其他页面')).toBeInTheDocument();
});

function PrefilledEditor({revision}:{revision:number}) {
 const [form]=Form.useForm();
 const draft=useCrfDraft({form,recordKey:'prefill-1',serverValues:{note:null,revision},prefillValues:{note:'系统值',revision},prefillNames:[['note']]});
 return <Form form={form}><Form.Item name='note'><Input aria-label='系统字段'/></Form.Item><button onClick={()=>draft.resetAfterSubmit(draft.getValues(),'prefill-1')}>保存快照</button></Form>;
}
it('keeps a saved explicit clear during same-record refetch instead of prefilling again',async()=>{
 const view=render(<PrefilledEditor revision={1}/>);
 expect(await screen.findByLabelText('系统字段')).toHaveValue('系统值');
 fireEvent.change(screen.getByLabelText('系统字段'),{target:{value:''}});
 fireEvent.click(screen.getByText('保存快照'));
 view.rerender(<PrefilledEditor revision={2}/>);
 expect(screen.getByLabelText('系统字段')).toHaveValue('');
});


function AsyncPrefilledEditor({doctor,date}:{doctor?:string;date?:string}) {
 const [form]=Form.useForm();
 const draft=useCrfDraft({form,recordKey:'async-prefill',serverValues:{},prefillValues:{doctor,date},prefillNames:[['doctor'],['date']]});
 return <Form form={form}><Form.Item name='doctor'><Input aria-label='异步医生'/></Form.Item><Form.Item name='date'><Input aria-label='异步入组日期'/></Form.Item><output>{JSON.stringify(draft.patch)}</output></Form>;
}
it.each(['doctor','date'])('fills later facts after %s arrives while preserving the edited first fact',async first=>{
 const view=render(<AsyncPrefilledEditor doctor={first==='doctor'?'当前医生':undefined} date={first==='date'?'2026-10-10':undefined}/>);
 const label=first==='doctor'?'异步医生':'异步入组日期';
 fireEvent.change(await screen.findByLabelText(label),{target:{value:''}});
 view.rerender(<AsyncPrefilledEditor doctor='当前医生' date='2026-10-10'/>);
 expect(screen.getByLabelText(label)).toHaveValue('');
 expect(screen.getByLabelText(first==='doctor'?'异步入组日期':'异步医生')).toHaveValue(first==='doctor'?'2026-10-10':'当前医生');
});
it('adds late enrollment after an untouched doctor prefill made the draft dirty',async()=>{
 const view=render(<AsyncPrefilledEditor doctor='当前医生'/>);
 expect(await screen.findByLabelText('异步医生')).toHaveValue('当前医生');
 view.rerender(<AsyncPrefilledEditor doctor='当前医生' date='2026-10-10'/>);
 expect(screen.getByLabelText('异步入组日期')).toHaveValue('2026-10-10');
});
function MarkedEditor({server}:{server:Record<string,unknown>}) {
 const [form]=Form.useForm();const draft=useCrfDraft({form,recordKey:'marked',serverValues:server});
 return <Form form={form}><Form.Item name='answer'><Input aria-label='值'/></Form.Item><button onClick={()=>{form.setFields([{name:['answer'],value:{__crf_answer__:1,state:'unknown',value:66,reason:null}}]);}}>不详</button><button onClick={()=>draft.resetAfterSubmit(draft.getValues(),'marked')}>保存答案</button><output data-testid='patch'>{JSON.stringify(draft.patch)}</output></Form>;
}
it('stays clean when database returns identical marked keys in a different order',async()=>{
 const view=render(<MarkedEditor server={{answer:66}}/>);
 fireEvent.click(screen.getByText('不详'));fireEvent.click(screen.getByText('保存答案'));
 expect(screen.getByTestId('patch')).toHaveTextContent('{}');
 view.rerender(<MarkedEditor server={{answer:{reason:null,value:66,state:'unknown',__crf_answer__:1}}}/>);
 expect(screen.getByTestId('patch')).toHaveTextContent('{}');
});
