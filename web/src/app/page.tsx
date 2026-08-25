"use client";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { Logo, Mark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ArrowRight, BarChart3, Brain, Eye, SlidersHorizontal, FileSpreadsheet, Lock } from "lucide-react";

const copy = {
  bg: {
    open_app: "Отвори приложението", sign_in: "Вход",
    tag: "AI аналитик за нетехнически екипи",
    h1a: "Качи екселите.", h1b: "Получи ", h1em: "жив дашборд", h1c: "Без формули. Без BI.",
    sub: "Bizzmind е личният аналитик на твоя търговски екип: качваш справките, AI-ят ги проучва, задава ти въпросите, които истински аналитик би задал — и строи табло с живи филтри, изводи и графики по твоите отговори.",
    cta: "Създай първия си проект", how: "Как работи", note: "Данните ти остават в изолирана среда за всеки проект.",
    how_kicker: "Как работи", how_title: "От ексел до дашборд в три стъпки",
    s1_h: "Качваш файловете", s1_p: "Ексели и CSV-та в реалния им вид — със заглавни редове, слети клетки, кирилица. Системата сама намира таблиците и колоните.",
    s1_pills: ["📄 продажби_2026.xlsx · 8 колони", "📄 цели_2026.xlsx · 3 колони", "📄 sell-out.csv · 4 колони"], s1_arrow: "↓ 12 таблици разпознати автоматично",
    s2_h: "AI-ят те интервюира", s2_p: "Проучва данните сам и пита само необходимото — с готови предложения, които избираш с един клик, или пишеш свой отговор. Като разговор с истински аналитик.",
    s2_q1: "В каква валута са оборотът и таргетът?", s2_o1: ["Евро (€)", "Лева (BGN)", "✎ Друг отговор"], s2_q2: "Кой показател е най-важен?", s2_o2: ["Оборот", "Изпълнение на таргета (%)"],
    s3_h: "Получаваш жив дашборд", s3_p: "Графики с истински филтри — по месец, човек, продукт, канал. Всяка промяна се преизчислява от базата на проекта, не от статични картинки.",
    s3_pills: ["Месец ▾", "Търговец ▾", "Продукт ▾", "€", "бройки"],
    why_kicker: "Защо Bizzmind", why_title: "Построен като истински аналитик, не като чатбот",
    b1_h: "Изводи, не само графики", b1_p: "AI-ят не спира до „ето ти графика“ — прави обобщение на целия анализ: наблюдение, число и конкретна препоръка на всеки ред, готово за отчета в понеделник.",
    b1_rows: [["Обща картина", "+6.8%", "ръстът идва изцяло от канала на едро — да се провери маржът"], ["Sell-out", "−3.7%", "трупат се запаси в канала — следи sell-in срещу sell-out"], ["Продукти", "топ 10 = 65%", "висока концентрация — разшири дистрибуцията на новите линии"]],
    b2_h: "Памет на проекта", b2_p: "Всеки отговор и откритие става знание — виждаш го, редактираш го, и AI-ят никога не пита два пъти.", b2_tags: ["валутата е евро", "T.E. = търговци → аптеки", "„Budget“ е факт, не цел"],
    b3_h: "Виждаш процеса", b3_p: "Никакво „мисля…“ на тъмно — всяка стъпка на AI-я тече на живо, с брояч на секундите.", b3_feed: ["🔍 Разглеждам: продажби по месеци…", "💾 Запомних: целите са в опаковки", "🎛 Филтър „Търговец“", "📊 Графика „Изпълнение на таргета“"],
    b4_h: "Живи филтри", b4_p: "AI-ят сам решава кои филтри заслужава таблото ти. Всяка промяна се преизчислява от базата на момента.",
    b5_h: "Реални ексели", b5_p: "Заглавни редове, слети клетки, двуредови хедъри, кирилица, дублирани колони — четем файловете такива, каквито излизат от ERP-то.",
    b6_h: "Изолирани проекти", b6_p: "Всеки проект е отделна среда с файлове, база, знание и дашборд. Нищо не се смесва; продължаваш откъдето си спрял.",
    cta_h: "Дай на екипа си личен аналитик", cta_p: "Първият дашборд е на минути разстояние — качи една справка и виж сам.", cta_btn: "Започни сега",
    footer: "Bizzmind — decisions, not dashboards.",
  },
  en: {
    open_app: "Open the app", sign_in: "Sign in",
    tag: "AI analyst for non-technical teams",
    h1a: "Upload your spreadsheets.", h1b: "Get a ", h1em: "live dashboard", h1c: "No formulas. No BI.",
    sub: "Bizzmind is the personal analyst of your sales team: you upload the reports, the AI explores them, asks the questions a real analyst would ask — and builds a board with live filters, insights and charts from your answers.",
    cta: "Create your first project", how: "How it works", note: "Your data stays in an isolated environment per project.",
    how_kicker: "How it works", how_title: "From spreadsheet to dashboard in three steps",
    s1_h: "Upload your files", s1_p: "Excel and CSV files as they really are — title rows, merged cells, any alphabet. The system finds the tables and columns on its own.",
    s1_pills: ["📄 sales_2026.xlsx · 8 columns", "📄 targets_2026.xlsx · 3 columns", "📄 sell-out.csv · 4 columns"], s1_arrow: "↓ 12 tables recognised automatically",
    s2_h: "The AI interviews you", s2_p: "It explores the data itself and asks only what it needs — with ready suggestions you pick with one click, or your own answer. Like talking to a real analyst.",
    s2_q1: "Which currency are revenue and target in?", s2_o1: ["Euro (€)", "Lev (BGN)", "✎ Other"], s2_q2: "Which metric matters most?", s2_o2: ["Revenue", "Target achievement (%)"],
    s3_h: "You get a live dashboard", s3_p: "Charts with real filters — by month, person, product, channel. Every change is recomputed from the project database, not from static pictures.",
    s3_pills: ["Month ▾", "Rep ▾", "Product ▾", "€", "units"],
    why_kicker: "Why Bizzmind", why_title: "Built like a real analyst, not a chatbot",
    b1_h: "Insights, not just charts", b1_p: "The AI doesn't stop at \"here's a chart\" — it summarises the whole analysis: an observation, a number and a concrete recommendation on every line, ready for Monday's report.",
    b1_rows: [["Big picture", "+6.8%", "growth comes entirely from the wholesale channel — check the margin"], ["Sell-out", "−3.7%", "stock is piling up in the channel — watch sell-in vs sell-out"], ["Products", "top 10 = 65%", "high concentration — widen distribution of the new lines"]],
    b2_h: "Project memory", b2_p: "Every answer and discovery becomes knowledge — you see it, edit it, and the AI never asks twice.", b2_tags: ["currency is EUR", "T.E. = reps → pharmacies", "\"Budget\" is a fact, not a target"],
    b3_h: "You see the process", b3_p: "No \"thinking…\" in the dark — every AI step streams live, with a seconds counter.", b3_feed: ["🔍 Exploring: sales by month…", "💾 Noted: targets are in packs", "🎛 Filter \"Rep\"", "📊 Chart \"Target achievement\""],
    b4_h: "Live filters", b4_p: "The AI decides which filters your board deserves. Every change is recomputed from the database on the spot.",
    b5_h: "Real spreadsheets", b5_p: "Title rows, merged cells, two-row headers, Cyrillic, duplicate columns — we read files the way they come out of the ERP.",
    b6_h: "Isolated projects", b6_p: "Every project is a separate environment with files, database, knowledge and dashboard. Nothing mixes; you continue where you left off.",
    cta_h: "Give your team a personal analyst", cta_p: "The first dashboard is minutes away — upload one report and see for yourself.", cta_btn: "Start now",
    footer: "Bizzmind — decisions, not dashboards.",
  },
} as const;

export default function Landing() {
  const { lang, setLang } = useLang();
  const c = copy[lang];
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-6 py-3">
          <Logo size={28} />
          <span className="flex-1" />
          <div className="inline-flex overflow-hidden rounded-lg border border-border text-[11px] font-extrabold">
            {(["bg", "en"] as const).map((l) => (
              <button key={l} type="button" onClick={() => setLang(l)} className={`px-2.5 py-1.5 ${lang === l ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{l.toUpperCase()}</button>
            ))}
          </div>
          <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/login" />}>{c.sign_in}</Button>
          <Button size="sm" className="grad-olive font-bold text-primary-foreground" nativeButton={false} render={<Link href="/app" />}>{c.open_app}</Button>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-olive/10 blur-3xl" />
        <div className="mx-auto grid w-full max-w-6xl gap-10 px-6 pb-16 pt-20 lg:grid-cols-[1.05fr_1fr] lg:items-center">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-olive/30 bg-olive/10 px-3 py-1 text-xs font-bold text-olive">
              <Mark size={16} />{c.tag}
            </div>
            <h1 className="text-4xl font-extrabold leading-[1.1] sm:text-5xl lg:text-[56px]">
              {c.h1a}<br />{c.h1b}<span className="text-grad-olive">{c.h1em}</span>.<br />{c.h1c}
            </h1>
            <p className="mt-6 max-w-xl text-[15.5px] leading-relaxed text-muted-foreground">{c.sub}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" className="grad-olive font-bold text-primary-foreground hover:opacity-90" nativeButton={false} render={<Link href="/app" />}>{c.cta}<ArrowRight className="size-4" /></Button>
              <Button size="lg" variant="outline" nativeButton={false} render={<a href="#how" />}>{c.how}</Button>
            </div>
            <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><Lock className="size-3.5" />{c.note}</div>
          </div>
          <div className="rounded-2xl border border-border bg-card p-2 shadow-[0_30px_80px_rgba(0,0,0,0.45)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/shots/dashboard_zoom.png" alt="" className="w-full rounded-xl" />
          </div>
        </div>
      </section>

      <section id="how" className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-xs font-bold uppercase tracking-wider text-olive">{c.how_kicker}</div>
        <h2 className="mt-2 text-3xl font-extrabold">{c.how_title}</h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <Step n={1} h={c.s1_h} p={c.s1_p}>
            <div className="flex flex-col gap-1.5">
              {c.s1_pills.map((x) => <span key={x} className="rounded-lg border border-border bg-secondary/60 px-2.5 py-1.5 text-xs">{x}</span>)}
              <div className="mt-1 text-xs font-semibold text-olive">{c.s1_arrow}</div>
            </div>
          </Step>
          <Step n={2} h={c.s2_h} p={c.s2_p}>
            <div className="text-xs font-semibold">{c.s2_q1}</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">{c.s2_o1.map((o, i) => <Chip key={o} on={i === 0}>{o}</Chip>)}</div>
            <div className="mt-3 text-xs font-semibold">{c.s2_q2}</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">{c.s2_o2.map((o, i) => <Chip key={o} on={i === 1}>{o}</Chip>)}</div>
          </Step>
          <Step n={3} h={c.s3_h} p={c.s3_p}>
            <div className="flex flex-wrap gap-1.5">{c.s3_pills.map((o, i) => <Chip key={o} on={i === 3}>{o}</Chip>)}</div>
            <svg viewBox="0 0 260 74" className="mt-3 w-full" aria-hidden="true">
              <g fill="#7f9c3a">{[[6, 34, 36], [32, 24, 46], [58, 40, 30], [84, 16, 54], [110, 28, 42], [136, 10, 60]].map(([x, y, h]) => <rect key={x} x={x} y={y} width="16" height={h} rx="3" />)}</g>
              <polyline points="170,52 192,38 214,44 236,20 254,26" fill="none" stroke="#c9e356" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              <g fill="#c9e356">{[[170, 52], [192, 38], [214, 44], [236, 20], [254, 26]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="3.4" />)}</g>
            </svg>
          </Step>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-xs font-bold uppercase tracking-wider text-olive">{c.why_kicker}</div>
        <h2 className="mt-2 text-3xl font-extrabold">{c.why_title}</h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <Bento icon={<BarChart3 />} h={c.b1_h} p={c.b1_p} className="md:col-span-2">
            <div className="mt-4 grid gap-2 text-xs">
              {c.b1_rows.map(([l, v, tx]) => (
                <div key={l} className="grid grid-cols-[110px_90px_1fr] items-baseline gap-3 rounded-lg border border-border bg-secondary/50 px-3 py-2">
                  <span className="font-bold text-muted-foreground">{l}</span><b className="text-olive">{v}</b><i className="text-muted-foreground">{tx}</i>
                </div>
              ))}
            </div>
          </Bento>
          <Bento icon={<Brain />} h={c.b2_h} p={c.b2_p}>
            <div className="mt-4 flex flex-wrap gap-1.5">{c.b2_tags.map((x) => <Chip key={x}>{x}</Chip>)}</div>
          </Bento>
          <Bento icon={<Eye />} h={c.b3_h} p={c.b3_p}>
            <ul className="mt-4 space-y-1 text-xs text-muted-foreground">{c.b3_feed.map((x) => <li key={x}>{x}</li>)}</ul>
          </Bento>
          <Bento icon={<SlidersHorizontal />} h={c.b4_h} p={c.b4_p}>
            <div className="mt-4 flex flex-wrap gap-1.5">{c.s3_pills.map((x) => <Chip key={x}>{x}</Chip>)}</div>
          </Bento>
          <Bento icon={<FileSpreadsheet />} h={c.b5_h} p={c.b5_p} />
          <Bento icon={<Lock />} h={c.b6_h} p={c.b6_p} className="md:col-span-3" />
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-20 pt-6">
        <div className="grad-olive rounded-3xl p-10 text-center text-primary-foreground">
          <h2 className="text-3xl font-extrabold">{c.cta_h}</h2>
          <p className="mt-2 opacity-80">{c.cta_p}</p>
          <Button size="lg" variant="secondary" className="mt-6 font-bold" nativeButton={false} render={<Link href="/app" />}>{c.cta_btn}<ArrowRight className="size-4" /></Button>
        </div>
      </section>

      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">{c.footer}</footer>
    </div>
  );
}

function Step({ n, h, p, children }: { n: number; h: string; p: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6">
      <div className="grad-olive inline-flex size-9 items-center justify-center rounded-xl text-sm font-extrabold text-primary-foreground">{n}</div>
      <div className="rounded-xl border border-border bg-background/60 p-3">{children}</div>
      <h3 className="text-lg font-bold">{h}</h3>
      <p className="text-[13.5px] leading-relaxed text-muted-foreground">{p}</p>
    </div>
  );
}

function Bento({ icon, h, p, children, className = "" }: { icon: React.ReactNode; h: string; p: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-border bg-card p-6 ${className}`}>
      <div className="mb-3 inline-flex size-10 items-center justify-center rounded-xl border border-olive/30 bg-olive/10 text-olive [&_svg]:size-5">{icon}</div>
      <h3 className="text-lg font-bold">{h}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">{p}</p>
      {children}
    </div>
  );
}

function Chip({ children, on }: { children: React.ReactNode; on?: boolean }) {
  return <span className={`rounded-full border px-2.5 py-1 text-xs ${on ? "border-olive bg-olive/15 text-foreground" : "border-border text-muted-foreground"}`}>{children}</span>;
}
