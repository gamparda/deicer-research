"""Reproducible deicer study. Run: python analyze.py

Published data are preserved separately from assumptions. No synthetic observations.
All modeled masses are kg; temperatures are deg C; costs are KRW.
"""
from pathlib import Path
import json, csv, hashlib, shutil
from io import StringIO
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.interpolate import PchipInterpolator
from lxml import html
import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager

ROOT = Path(__file__).resolve().parent
DATA, OUT, SRC = (ROOT / x for x in ('data', 'outputs', 'sources'))
for p in (DATA, OUT, SRC): p.mkdir(exist_ok=True)
FONT = SRC/'NanumGothic-Regular.ttf'
if FONT.exists():
    fontManager.addfont(str(FONT))
    plt.rcParams['font.family'] = FontProperties(fname=str(FONT)).get_name()
plt.rcParams.update({'axes.unicode_minus':False,'font.size':10,'savefig.dpi':190})
FCL = {'NaCl':35.45/(22.98976928+35.45), 'CaCl2':70.90/(40.078+70.90),
       'MgCl2':70.90/(24.305+70.90)}
A_DIHYDRATE = 110.978/(110.978+2*18.01528)
URLS = {
 'ASHRAE2017':'https://handbook.ashrae.org/handbooks/F17/SI/f17_ch31/f17_ch31_si.aspx',
 'ASHRAE2025':'https://handbook.ashrae.org/Handbooks/F25/SI/f25_Ch31/f25_Ch31_si.aspx',
 'OXY2026':'https://www.oxychemcalciumchloride.com/siteassets/documents/guides/calcium-chloride-handbook.pdf',
 'CR18_06':'https://depts.washington.edu/trac/bulkdisk/pdf/FinalReport_CR.18-06_Final.pdf',
 'GWANGJU2025':'https://www.bidpro.co.kr/n0_ipchal/konggo/item/konggo_view.asp?num=5299613'}

def number(s): return float(s.replace('−','-').replace('–','-').replace(',',''))

def get_tables(name):
    return html.fromstring((SRC/name).read_bytes()).xpath('//table')

points=[]
def add(source,chemical,w,t,location,unit='C',value=None):
    points.append(dict(source_id=source,chemical=chemical,mass_fraction=w,
                       freezing_temperature_c=t,source_location=location,
                       original_unit=unit,original_value=t if value is None else value,
                       source_url=URLS['OXY2026' if source.startswith('OXY') else source]))

if not ((SRC/'ashrae2017.html').exists() and (SRC/'ashrae2025.html').exists() and (SRC/'oxy2026.pdf').exists()):
    phase=pd.read_csv(DATA/'phase_points.csv')
else:
    for idx, chem, cutoff in [(0,'CaCl2',29.87),(1,'NaCl',23)]:
        for tr in get_tables('ashrae2017.html')[idx].xpath('.//tr')[2:]:
            cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')]
            try: w,t=number(cells[0]),number(cells[2])
            except (ValueError,IndexError): continue
            if 0<=w<=cutoff:add('ASHRAE2017',chem,w/100,t,f'Table {idx+1}, {w:g} wt%')

    for tr in get_tables('ashrae2025.html')[3].xpath('.//tr')[1:]:
        cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')]
        try: w,t=number(cells[0]),number(cells[-1])
        except (ValueError,IndexError): continue
        if 0<w<=22:add('ASHRAE2025','NaCl',w/100,t,f'Table 2A, {w:g} wt%')

    pdf=fitz.open(SRC/'oxy2026.pdf')
    for page, sid, unit in [(21,'OXY2026_F','F'),(22,'OXY2026_C','C')]:
        s=pdf[page].get_text().split('Boiling Point',1)[1].split('0 \n1.000',1)[1]
        # Seven tokens per row: wt%, SG, density, volume/solution, volume/salt, freeze, boil.
        tokens=('0 \n1.000'+s).split()
        vals=[]
        for tok in tokens:
            try: vals.append(number(tok) if tok!='n/a' else np.nan)
            except ValueError: break
        assert len(vals)>=31*7,(sid,len(vals))
        for j in range(0,len(vals)-6,7):
            w=vals[j]; original=vals[j+5]
            if w>29.6:break
            t=(original-32)*5/9 if unit=='F' else original
            add(sid,'CaCl2',w/100,t,f'Table 3{"a" if unit=="F" else "b"}, PDF p.{page+1}',unit,original)

    phase=pd.DataFrame(points)
    phase.to_csv(DATA/'phase_points.csv',index=False)

def curve(source,chemical):
    df=phase[(phase.source_id==source)&(phase.chemical==chemical)].sort_values('mass_fraction')
    w=df.mass_fraction.to_numpy(); t=df.freezing_temperature_c.to_numpy()
    assert len(w)>3 and np.all(np.diff(w)>0) and np.all(np.diff(t)<=0)
    return w,t

def wcrit(T,source,chem,method='linear'):
    w,t=curve(source,chem)
    if T>t[0]+1e-9 or T<t[-1]-1e-9:raise ValueError(f'Outside source domain: {source} {chem} {T}')
    if method=='pchip':
        fn=PchipInterpolator(w,t)
        return brentq(lambda x:fn(x)-T,w[0],w[-1],xtol=1e-13)
    for j in range(len(w)-1):
        if t[j]>=T>=t[j+1]:
            if t[j]==T:return float(w[j])
            return float(w[j]+(w[j+1]-w[j])*(t[j]-T)/(t[j]-t[j+1]))
    return float(w[-1])

def required(w,a=1,h=0,W=1):
    denom=a*(1-w)-w*h
    if denom<=0: raise ValueError('Infeasible product composition')
    Q=W*w/denom
    reconstructed=a*Q/(W+(a+h)*Q)
    assert abs(reconstructed-w)<1e-12
    return Q

SETS={'동일편람2017':('ASHRAE2017','ASHRAE2017'),
      '제조사F+Na2025':('ASHRAE2025','OXY2026_F'),
      '제조사C+Na2025':('ASHRAE2025','OXY2026_C')}
records=[]
for setname,(ns,cs) in SETS.items():
    for T in np.round(np.arange(-18,-2.999,.1),6):
        wn,wc=wcrit(T,ns,'NaCl'),wcrit(T,cs,'CaCl2')
        qn,qc=required(wn),required(wc)
        qh=required(wc,A_DIHYDRATE,1-A_DIHYDRATE)
        records.append(dict(source_set=setname,temperature_c=T,nacl_w=wn,cacl2_w=wc,
                            nacl_pure_g=qn*1000,cacl2_pure_g=qc*1000,cacl2_dihydrate_g=qh*1000,
                            nacl_chloride_g=qn*FCL['NaCl']*1000,
                            cacl2_pure_chloride_g=qc*FCL['CaCl2']*1000,
                            cacl2_dihydrate_chloride_g=qh*A_DIHYDRATE*FCL['CaCl2']*1000,
                            pure_price_break_even=qn/qc,dihydrate_price_break_even=qn/qh))
grid=pd.DataFrame(records);grid.to_csv(OUT/'equilibrium_grid.csv',index=False)
key=grid[grid.temperature_c.isin([-5,-10,-15,-18])].copy()
key.to_csv(OUT/'key_results.csv',index=False)

# One published purchase notice, budget unit prices. Not contract or market prices.
notice=json.loads((DATA/'purchase_notice.json').read_text())
prices={item['chemical']:item['budget_krw']/item['mass_kg'] for item in notice['items']}
pd.DataFrame([dict(chemical=c,price_krw_per_kg=p,active_fraction_min=.85 if c=='NaCl' else .74,
                   price_type='2025_notice_budget_not_awarded_contract',source_url=URLS['GWANGJU2025'])
              for c,p in prices.items()]).to_csv(DATA/'budget_prices.csv',index=False)
purchase=[]
for r in key.to_dict('records'):
    for hn in [0,.15]:
        for hc in [0,.26]:
            qn=required(r['nacl_w'],.85,hn);qc=required(r['cacl2_w'],.74,hc)
            purchase.append(dict(source_set=r['source_set'],temperature_c=r['temperature_c'],
              nacl_active=.85,cacl2_active=.74,nacl_water_fraction=hn,cacl2_water_fraction=hc,
              nacl_product_g=qn*1000,cacl2_product_g=qc*1000,
              nacl_cost_krw=qn*prices['NaCl'],cacl2_cost_krw=qc*prices['CaCl2'],
              ca_to_na_cost_ratio=qc*prices['CaCl2']/(qn*prices['NaCl']),
              price_ratio_break_even=qn/qc,
              assumption='remaining_fraction_is_water_or_noninteracting_insoluble_inert'))
purchase=pd.DataFrame(purchase);purchase.to_csv(OUT/'budget_application.csv',index=False)

# Equal expenditure scenario: price per kg is normalized equal; 0.25 kg each, external water 1 kg.
dil=[]
for setname,(ns,cs) in SETS.items():
    for chem,a,h,source in [('NaCl',1,0,ns),('CaCl2',A_DIHYDRATE,1-A_DIHYDRATE,cs)]:
        Q=.25; W=1; salt=a*Q; water=W+h*Q; liquid=salt+water
        w0=salt/liquid;cw,ct=curve(source,chem)
        assert cw[0]<=w0<=cw[-1]  # starting composition on the selected dilute branch
        initial_tf=float(np.interp(w0,cw,ct))
        for T in [-5,-10,-15,-18]:
            threshold=wcrit(T,source,chem)
            extra=salt/threshold-liquid
            dil.append(dict(source_set=setname,chemical=chem,temperature_c=T,
                            external_water_kg=W,product_kg=Q,active_fraction=a,
                            initial_mass_fraction=w0,initial_freezing_point_c=initial_tf,
                            additional_water_to_boundary_kg=extra,
                            initially_satisfies=bool(w0>=threshold)))
pd.DataFrame(dil).to_csv(OUT/'equal_budget_dilution.csv',index=False)

# Interpolation sensitivity uses the same observations, with no new physical data.
interp=[]
for setname,(ns,cs) in SETS.items():
    if setname=='제조사C+Na2025':continue # integer-C plateaus are deliberately not spline-smoothed
    for T in [-5,-10,-15,-18]:
        wl=[wcrit(T,ns,'NaCl'),wcrit(T,cs,'CaCl2')]
        wp=[wcrit(T,ns,'NaCl','pchip'),wcrit(T,cs,'CaCl2','pchip')]
        for chem,l,p in zip(['NaCl','CaCl2'],wl,wp):
            interp.append(dict(source_set=setname,temperature_c=T,chemical=chem,
                               linear_w=l,pchip_w=p,difference_percentage_points=100*(p-l)))
pd.DataFrame(interp).to_csv(OUT/'interpolation_sensitivity.csv',index=False)

# Actual repeated laboratory measurements; no NaCl-to-CaCl2 cross-temperature ranking.
old=ROOT.parent/'deicer_research_plan/data/imc_observations.csv'
if not (DATA/'imc_observations.csv').exists():
    shutil.copy2(old,DATA/'imc_observations.csv')
obs=pd.read_csv(DATA/'imc_observations.csv')
assert len(obs)==120 and len(obs.drop_duplicates(['chemical','group','replicate']))==120
rng=np.random.default_rng(20261021); nboot=30000
bsrows=[];leave=[];groupdata=[]
for subset,groups in [('source_selected',['L1','L2','L4','L6','L7']),('all_reported',[f'L{i}' for i in range(1,9)])]:
    arrays={c:np.stack([obs[(obs.chemical==c)&(obs.group==g)].imc_g_per_ml.to_numpy() for g in groups])
            for c in ['CaCl2','MgCl2']}
    k=len(groups);grpidx=rng.integers(0,k,size=(nboot,k))
    boot={}
    for c,arr in arrays.items():
        ridx=rng.integers(0,5,size=(nboot,k,5))
        boot[c]=arr[grpidx[:,:,None],ridx].mean(axis=(1,2))
    ratio=boot['MgCl2']/boot['CaCl2']
    ci=np.quantile(ratio,[.025,.975])
    bsrows.append(dict(subset=subset,groups=k,observations_per_chemical=k*5,
                        ca32_imc_mean=arrays['CaCl2'].mean(),mg29_imc_mean=arrays['MgCl2'].mean(),
                        ratio_mg_to_ca=arrays['MgCl2'].mean()/arrays['CaCl2'].mean(),
                        ratio_bootstrap_low=ci[0],ratio_bootstrap_high=ci[1],
                        resamples=nboot,seed=20261021,conditioning_temperature_f=0,duration_min=15))
    for j,g in enumerate(groups):
        remaining=[i for i in range(k) if i!=j]
        leave.append(dict(subset=subset,omitted_group=g,
                            ratio_mg_to_ca=arrays['MgCl2'][remaining].mean()/arrays['CaCl2'][remaining].mean()))
        for c,arr in arrays.items():groupdata.append(dict(subset=subset,group=g,chemical=c,
                                                        mean=arr[j].mean(),sd=arr[j].std(ddof=1)))
pd.DataFrame(bsrows).to_csv(OUT/'imc_bootstrap.csv',index=False)
pd.DataFrame(leave).to_csv(OUT/'imc_leave_one_group_out.csv',index=False)
pd.DataFrame(groupdata).to_csv(OUT/'imc_group_results.csv',index=False)

def save(fig,name):
    fig.savefig(OUT/(name+'.png'),bbox_inches='tight')
    fig.savefig(OUT/(name+'.svg'),bbox_inches='tight')
    plt.close(fig)

base=grid[grid.source_set=='동일편람2017']
fig,ax=plt.subplots(figsize=(8,4.5))
for chem,color in [('NaCl','#2563a6'),('CaCl2','#bd6422')]:
    w,t=curve('ASHRAE2017',chem); m=t>=-25
    ax.plot(w[m]*100,t[m],'o-',ms=3,label=chem,color=color)
ax.set(xlabel='무수 염의 질량백분율 (%)',ylabel='결빙 개시 온도 (°C)',title='동일 편람의 농도–결빙 개시 온도 자료')
ax.legend();ax.grid(alpha=.2);fig.tight_layout();save(fig,'01_phase_curves')

fig,axes=plt.subplots(1,2,figsize=(11,4.5))
for col,label,col2 in [('nacl_pure_g','NaCl (무수)','nacl_chloride_g'),
                       ('cacl2_pure_g','CaCl2 (무수)','cacl2_pure_chloride_g'),
                       ('cacl2_dihydrate_g','CaCl2·2H2O','cacl2_dihydrate_chloride_g')]:
    axes[0].plot(-base.temperature_c,base[col],label=label)
    axes[1].plot(-base.temperature_c,base[col2],label=label)
for ax in axes:ax.set_xlabel('목표 온도의 절댓값 (°C)');ax.grid(alpha=.2);ax.legend(fontsize=9)
axes[0].set(ylabel='필요 제품 질량 (g)',title='외부 물 1 kg당 최소 필요량')
axes[1].set(ylabel='염화물 투입 질량 (g)',title='같은 결빙 억제 조건의 염화물 양')
fig.tight_layout();save(fig,'02_mass_and_chloride')

fig,ax=plt.subplots(figsize=(8,4.8))
for sn,grp in grid.groupby('source_set',sort=False):
    ax.plot(-grp.temperature_c,grp.dihydrate_price_break_even,label=sn)
ax.axhline(1,color='gray',ls='--',lw=1)
ax.set(xlabel='목표 온도의 절댓값 (°C)',ylabel='CaCl2·2H2O / NaCl의 kg당 가격비',
       title='이 선보다 가격비가 낮으면 CaCl2·2H2O 재료비가 낮음')
ax.legend();ax.grid(alpha=.2);fig.tight_layout();save(fig,'03_price_boundaries')

fig,ax=plt.subplots(figsize=(8,4.8))
x=-base.temperature_c.to_numpy(); pr=np.linspace(.4,2.2,200)
boundary=base.dihydrate_price_break_even.to_numpy()
ax.pcolormesh(x,pr,np.where(pr[:,None]<boundary[None,:],1,0),shading='auto',cmap=matplotlib.colors.ListedColormap(['#dbeafe','#ffddb5']))
ax.plot(x,boundary,color='black',lw=1.2)
ax.text(12,1.6,'NaCl의 재료비가 낮음',ha='center')
ax.text(12,.5,'CaCl2·2H2O의 재료비가 낮음',ha='center')
ax.set(xlabel='목표 온도의 절댓값 (°C)',ylabel='CaCl2·2H2O / NaCl의 kg당 가격비',title='외부 물 1 kg 기준 재료비 선택 지도 (동일편람2017)')
fig.tight_layout();save(fig,'04_decision_map')

fig,ax=plt.subplots(figsize=(8,4.5))
for sn,grp in grid.groupby('source_set',sort=False):
    diff=100*(grp.cacl2_pure_chloride_g/grp.nacl_chloride_g-1)
    ax.plot(-grp.temperature_c,diff,label=sn)
ax.axhline(0,color='black',lw=1)
ax.set(xlabel='목표 온도의 절댓값 (°C)',ylabel='무수 CaCl2의 염화물 차이 (%)',title='염화물 우열은 물성 자료 선택에 민감함: 양수이면 CaCl2가 많음')
ax.legend();ax.grid(alpha=.2);fig.tight_layout();save(fig,'05_source_sensitivity')

fig,ax=plt.subplots(figsize=(8,4.8))
g=pd.DataFrame(groupdata);g=g[g.subset=='source_selected'];names=['L1','L2','L4','L6','L7']
for c,off,label in [('CaCl2',-.07,'CaCl2 32%'),('MgCl2',.07,'MgCl2 29%')]:
    a=g[g.chemical==c].set_index('group').loc[names]
    ax.errorbar(np.arange(5)+off,a['mean'],yerr=a['sd'],fmt='o',capsize=4,label=label)
ax.set_xticks(range(5),names)
ax.set(xlabel='시험그룹 (각 물질 5회 반복)',ylabel='융빙량 / 투입 용액 부피 (g/mL)',title='0°F 준비 조건, 15분 절차의 공개 실험 재분석')
ax.legend();ax.grid(alpha=.2);fig.tight_layout();save(fig,'06_imc_observations')

fig,ax=plt.subplots(figsize=(8,4.8))
added=np.linspace(0,.8,161)
for chem,a,h,label in [('NaCl',1,0,'NaCl 250 g'),
                       ('CaCl2',A_DIHYDRATE,1-A_DIHYDRATE,'CaCl2·2H2O 250 g')]:
    wc,tc=curve('ASHRAE2017',chem)
    conc=a*.25/(1+.25+added)
    tf=np.interp(conc,wc,tc)
    ax.plot(added*1000,tf,label=label)
ax.axhline(-10,color='black',ls='--',label='목표 온도 -10°C')
ax.set(xlabel='추가 물 질량 (g)',ylabel='용액의 결빙 개시 온도 (°C)',
       title='외부 물 1 kg에 각 제품 250 g: kg당 가격이 같을 때 같은 예산')
ax.legend();ax.grid(alpha=.2);fig.tight_layout();save(fig,'07_dilution')

# Meaningful validation: manual anchor concentrations + domain handling + mass conservation.
assert abs(wcrit(-5,'ASHRAE2017','NaCl')-.08)<1e-12
assert abs(wcrit(-10,'ASHRAE2017','NaCl')-.139)<1e-12
assert abs(wcrit(-10,'ASHRAE2017','CaCl2')-(.14+.01*.8/1.1))<1e-12
assert abs(required(.2)-.25)<1e-12
assert abs(required(.2,A_DIHYDRATE,1-A_DIHYDRATE)-(.2/(A_DIHYDRATE-.2)))<1e-12
try:wcrit(-40,'ASHRAE2017','NaCl')
except ValueError:pass
else:raise AssertionError('Extrapolation was not blocked')

audit=[
 {'item':'ASHRAE2017','decision':'primary','reason':'Same-edition tables for both salts; use dilute branch only.'},
 {'item':'OXY2026_F + ASHRAE2025 Na','decision':'alternative_source_scenario','reason':'Manufacturer typical properties; integer-F converted to C; not pooled with pure brine data.'},
 {'item':'OXY2026_C','decision':'rounding_source_sensitivity','reason':'Integer-C tabulation has plateaus and differs from converted F table.'},
 {'item':'ASHRAE2025 CaCl2 Table 1A','decision':'not_used_for_main_conclusion','reason':'Concentrated phase branch conflicts with other sources; cause unresolved.'},
 {'item':'FHWA Appendix B -10C examples','decision':'context_only','reason':'Approximate graph-derived examples disagree with Appendix A tabulated values.'},
 {'item':'2025 Gwangju notice','decision':'budget_price_scenario','reason':'Reposted notice, not awarded contract. Minimum active fractions are modeled; actual composition unknown.'},
 {'item':'IMC NaCl vs Ca/Mg','decision':'cross_temperature_ranking_excluded','reason':'15 F vs 0 F.'},
 {'item':'IMC density-to-chloride conversion','decision':'not_computed','reason':'Compatible volume-metering density and temperature not established.'}]
(OUT/'data_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
summary=dict(date='2026-10-21',water_basis='external water 1 kg',
              a_dihydrate=A_DIHYDRATE,chloride_fractions=FCL,phase_rows=len(phase),
              grid_rows=len(grid),observations=120,bootstrap=bsrows,prices=prices,
              price_ratio=prices['CaCl2']/prices['NaCl'],
              key_results=key.to_dict('records'),
              budget_at_minus10=purchase[purchase.temperature_c==-10].to_dict('records'),
              validation='passed: manual anchors, mass balance, no extrapolation, observation counts')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*')}
(OUT/'input_sha256.json').write_text(json.dumps(manifest,indent=2))
print(key[['source_set','temperature_c','nacl_pure_g','cacl2_pure_g','cacl2_dihydrate_g','dihydrate_price_break_even']].round(4).to_string(index=False))
print('\nBOOTSTRAP\n',pd.DataFrame(bsrows).round(5).to_string(index=False))
print('\nBUDGET EXAMPLE AT -10 C\n',purchase[purchase.temperature_c==-10].groupby('source_set')[['nacl_cost_krw','cacl2_cost_krw','ca_to_na_cost_ratio']].agg(['min','max']).round(3).to_string())
print('\nVALIDATION PASSED')
