"use client";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { Logo, Mark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ArrowRight, BarChart3, Blocks, Brain, Check, SlidersHorizontal, FileSpreadsheet, Lock } from "lucide-react";
import { ThemeToggle } from "@/lib/theme";

const copy = {
  bg: {
    open_app: "Отвори приложението", sign_in: "Вход",
    tag: "За малки и средни фирми, които още смятат в ексел",
    h1a: "Отчетът, който правите", h1b: "на ръка всеки месец —", h1em: "готов преди кафето", h1c: "",
    sub: "Качвате справките както излизат от ERP-то, касовия апарат или счетоводството. AI аналитик ги проучва, пита ви това, което истинският аналитик би питал, и връща таблото с изводите — на български, за минути.",
    cta: "Опитай безплатно", how: "Виж как работи", demo_cta: "Виж живо демо", demo_nav: "Демо", note: "Данните ви остават в ЕС (Ирландия и Франкфурт) и не обучават AI модели.",
    proof: ["слети клетки", "двуредови хедъри", "кирилица", ".xls от 2003", "по един лист на обект", "45 таблици в един файл"],
    proof_lead: "Четем файловете такива, каквито са:",
    how_kicker: "Как работи", how_title: "От ексел до дашборд в три стъпки",
    s1_h: "Качваш файловете", s1_p: "Ексели и CSV-та в реалния им вид — със заглавни редове, слети клетки, кирилица. Системата сама намира таблиците и колоните.",
    s1_chrome: "Файлове и знание", s1_drop: "Пуснете екселите тук",
    s1_files: [["РАПОРТ 01.2024.xls", "45 листа"], ["продажби_2026.xlsx", "8 колони"], ["sell-out.csv", "4 колони"]],
    s1_arrow: "45 таблици · 2 419 реда — разпознати автоматично",
    s2_h: "AI-ят те интервюира", s2_p: "Проучва данните сам и пита само необходимото — с готови предложения, които избираш с един клик, или пишеш свой отговор. Като разговор с истински аналитик.",
    s2_chrome: "Разговор", s2_a: "Лева — и трите обекта",
    s2_q1: "В каква валута са оборотът и таргетът?", s2_o1: ["Евро (€)", "Лева (BGN)", "✎ Друг"], s2_q2: "Кой показател е най-важен?", s2_o2: ["Оборот", "Изпълнение на таргета"],
    s3_h: "Получаваш жив дашборд", s3_p: "Графики с истински филтри — по месец, човек, продукт, канал. Всяка промяна се преизчислява от базата на проекта, не от статични картинки.",
    s3_chrome: "Дашборд", s3_pills: ["Месец ▾", "Обект ▾", "Продукт ▾", "лв", "бройки"],
    s3_kpis: [["Оборот", "225 051 лв", "+6.8% спрямо декември"], ["Среден бон", "10.70 лв", "най-висок: Ямбол"]],
    why_kicker: "Защо Bizzmind", why_title: "Построен като истински аналитик, не като чатбот",
    b1_h: "Изводи, не само графики", b1_p: "AI-ят не спира до „ето ти графика“ — прави обобщение на целия анализ: наблюдение, число и конкретна препоръка на всеки ред, готово за отчета в понеделник.",
    b1_rows: [["Обща картина", "+6.8%", "ръстът идва изцяло от канала на едро — да се провери маржът"], ["Sell-out", "−3.7%", "трупат се запаси в канала — следи sell-in срещу sell-out"], ["Продукти", "топ 10 = 65%", "висока концентрация — разшири дистрибуцията на новите линии"]],
    b2_h: "Памет на проекта", b2_p: "Всеки отговор и откритие става знание — виждаш го, редактираш го, и AI-ят никога не пита два пъти.", b2_tags: ["валутата е евро", "T.E. = търговци → аптеки", "„Budget“ е факт, не цел"],
    b3_h: "Виждаш процеса", b3_p: "Никакво „мисля…“ на тъмно — всяка стъпка на AI-я тече на живо, с брояч на секундите.", b3_feed: ["🔍 Разглеждам: продажби по месеци…", "💾 Запомних: целите са в опаковки", "🎛 Филтър „Търговец“", "📊 Графика „Изпълнение на таргета“"],
    b4_h: "Живи филтри", b4_p: "AI-ят сам решава кои филтри заслужава таблото ти. Всяка промяна се преизчислява от базата на момента.",
    b5_h: "Реални ексели", b5_p: "Заглавни редове, слети клетки, двуредови хедъри, кирилица, дублирани колони — четем файловете такива, каквито излизат от ERP-то.",
    b6_h: "Изолирани проекти", b6_p: "Всеки проект е отделна среда с файлове, база, знание и дашборд. Нищо не се смесва; продължаваш откъдето си спрял.",
    b7_h: "Екселът става приложение", b7_p: "Освен таблото, AI-ят построява работен екран върху същите данни: форми за въвеждане вместо писане в клетки, живи показатели и списък „дни за проверка“. Спирате да пълните ексела.",
    b7_tags: ["Нов ден — Ямбол", "Оборот за деня", "Дни за проверка"],
    price_kicker: "Цени", price_title: "Плащате колкото ползвате",
    price_sub: "Кредитите се смятат от реално изхарченото, с прогноза преди всяко действие и таван, за да няма изненади. Без договор, спирате когато решите.",
    price_free_h: "Free", price_free_p: "1 проект · 1000 кредита еднократно", price_free_note: "Стигат за пълен цикъл: анализ, дашборд и презентация.",
    price_pro_h: "Pro", price_pro_p: "€25/мес · 10 проекта · 4000 кредита", price_pro_note: "Неизползваните се прехвърлят. Данните ви не обучават AI модели.",
    price_ultra_h: "Ultra", price_ultra_p: "€99/мес · 50 проекта · 20 000 кредита", price_ultra_note: "Max модел за сложни данни, обработка само в ЕС, приоритет.",
    price_cta: "Виж пълните цени",
    not_kicker: "Честно казано", not_title: "За кого не е",
    not_items: ["Имате data warehouse и BI екип — вече си решавате този проблем.", "Данните ви са в 200 таблици в SQL — още не сме за там.", "Търсите счетоводна програма или ERP — това не е нито едното."],
    for_title: "За кого е", for_items: ["Справките ви живеят в ексели и всеки период някой ги сглобява на ръка.", "Имате няколко обекта, канала или продуктови линии и ги сравнявате между тях.", "Решенията се взимат от тези числа, а няма кой да ги подреди."],
    cta_h: "Качете една справка и вижте", cta_p: "Първият дашборд е на минути разстояние. Безплатно, без карта.", cta_btn: "Започни безплатно",
    footer: "Bizzmind — decisions, not dashboards.",
  },
  en: {
    open_app: "Open the app", sign_in: "Sign in",
    tag: "For small and mid-sized companies still doing it in Excel",
    h1a: "The report you rebuild", h1b: "by hand every month —", h1em: "done before coffee", h1c: "",
    sub: "Upload the files exactly as they come out of your ERP, till system or accountant. An AI analyst explores them, asks what a real analyst would ask, and hands back the board with the conclusions — in minutes.",
    cta: "Try it free", how: "See how it works", demo_cta: "See the live demo", demo_nav: "Demo", note: "Your data stays in the EU (Ireland and Frankfurt) and never trains AI models.",
    proof: ["merged cells", "two-row headers", "any alphabet", ".xls from 2003", "one sheet per location", "45 tables in one file"],
    proof_lead: "We read files exactly as they are:",
    how_kicker: "How it works", how_title: "From spreadsheet to dashboard in three steps",
    s1_h: "Upload your files", s1_p: "Excel and CSV files as they really are — title rows, merged cells, any alphabet. The system finds the tables and columns on its own.",
    s1_chrome: "Files & knowledge", s1_drop: "Drop your spreadsheets here",
    s1_files: [["REPORT 01.2024.xls", "45 sheets"], ["sales_2026.xlsx", "8 columns"], ["sell-out.csv", "4 columns"]],
    s1_arrow: "45 tables · 2,419 rows — recognised automatically",
    s2_h: "The AI interviews you", s2_p: "It explores the data itself and asks only what it needs — with ready suggestions you pick with one click, or your own answer. Like talking to a real analyst.",
    s2_chrome: "Conversation", s2_a: "Leva — for all three sites",
    s2_q1: "Which currency are revenue and target in?", s2_o1: ["Euro (€)", "Lev (BGN)", "✎ Other"], s2_q2: "Which metric matters most?", s2_o2: ["Revenue", "Target achievement"],
    s3_h: "You get a live dashboard", s3_p: "Charts with real filters — by month, person, product, channel. Every change is recomputed from the project database, not from static pictures.",
    s3_chrome: "Dashboard", s3_pills: ["Month ▾", "Site ▾", "Product ▾", "BGN", "units"],
    s3_kpis: [["Turnover", "225,051 lv", "+6.8% vs December"], ["Avg. receipt", "10.70 lv", "highest: Yambol"]],
    why_kicker: "Why Bizzmind", why_title: "Built like a real analyst, not a chatbot",
    b1_h: "Insights, not just charts", b1_p: "The AI doesn't stop at \"here's a chart\" — it summarises the whole analysis: an observation, a number and a concrete recommendation on every line, ready for Monday's report.",
    b1_rows: [["Big picture", "+6.8%", "growth comes entirely from the wholesale channel — check the margin"], ["Sell-out", "−3.7%", "stock is piling up in the channel — watch sell-in vs sell-out"], ["Products", "top 10 = 65%", "high concentration — widen distribution of the new lines"]],
    b2_h: "Project memory", b2_p: "Every answer and discovery becomes knowledge — you see it, edit it, and the AI never asks twice.", b2_tags: ["currency is EUR", "T.E. = reps → pharmacies", "\"Budget\" is a fact, not a target"],
    b3_h: "You see the process", b3_p: "No \"thinking…\" in the dark — every AI step streams live, with a seconds counter.", b3_feed: ["🔍 Exploring: sales by month…", "💾 Noted: targets are in packs", "🎛 Filter \"Rep\"", "📊 Chart \"Target achievement\""],
    b4_h: "Live filters", b4_p: "The AI decides which filters your board deserves. Every change is recomputed from the database on the spot.",
    b5_h: "Real spreadsheets", b5_p: "Title rows, merged cells, two-row headers, Cyrillic, duplicate columns — we read files the way they come out of the ERP.",
    b6_h: "Isolated projects", b6_p: "Every project is a separate environment with files, database, knowledge and dashboard. Nothing mixes; you continue where you left off.",
    b7_h: "Your spreadsheet becomes an app", b7_p: "Beyond the board, the AI builds a working surface over the same data: entry forms instead of typing into cells, live metrics and a \"days to check\" list. You stop feeding the spreadsheet.",
    b7_tags: ["New day — Yambol", "Turnover today", "Days to check"],
    price_kicker: "Pricing", price_title: "You pay for what you use",
    price_sub: "Credits are settled from actual usage, with an estimate before every action and a cap so there are no surprises. No contract, stop whenever you like.",
    price_free_h: "Free", price_free_p: "1 project · 1000 credits, one-off", price_free_note: "Enough for a full cycle: analysis, dashboard and a presentation.",
    price_pro_h: "Pro", price_pro_p: "€25/mo · 10 projects · 4000 credits", price_pro_note: "Unused credits roll over. Your data never trains AI models.",
    price_ultra_h: "Ultra", price_ultra_p: "€99/mo · 50 projects · 20,000 credits", price_ultra_note: "Max model for complex data, EU-only processing, priority support.",
    price_cta: "See full pricing",
    not_kicker: "Honestly", not_title: "Who it is not for",
    not_items: ["You have a data warehouse and a BI team — you already solved this.", "Your data lives in 200 SQL tables — we are not there yet.", "You are looking for accounting software or an ERP — this is neither."],
    for_title: "Who it is for", for_items: ["Your reports live in spreadsheets and someone rebuilds them by hand every period.", "You run several locations, channels or product lines and compare them.", "Decisions are made from these numbers and nobody has time to arrange them."],
    cta_h: "Upload one report and see", cta_p: "The first dashboard is minutes away. Free, no card.", cta_btn: "Start free",
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
          <ThemeToggle />
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/demo" />} className="hidden sm:inline-flex">{c.demo_nav}</Button>
          <Button variant="ghost" size="sm" nativeButton={false} render={<a href="#pricing" />} className="hidden sm:inline-flex">{c.price_kicker}</Button>
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
            <h1 className="text-4xl font-extrabold leading-[1.1] sm:text-5xl lg:text-[54px]">
              {c.h1a}<br />{c.h1b}<br /><span className="text-grad-olive">{c.h1em}</span>.
            </h1>
            <p className="mt-6 max-w-xl text-[15.5px] leading-relaxed text-muted-foreground">{c.sub}</p>
            <div className="mt-5 flex flex-wrap items-center gap-1.5 text-xs">
              <span className="font-semibold text-foreground">{c.proof_lead}</span>
              {c.proof.map((x) => <Chip key={x}>{x}</Chip>)}
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" className="grad-olive font-bold text-primary-foreground hover:opacity-90" nativeButton={false} render={<Link href="/app" />}>{c.cta}<ArrowRight className="size-4" /></Button>
              <Button size="lg" variant="outline" nativeButton={false} render={<Link href="/demo" />}>{c.demo_cta}</Button>
            </div>
            <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><Lock className="size-3.5" />{c.note}</div>
          </div>
          <Link href="/demo" className="group relative block rounded-2xl border border-border bg-card p-2 shadow-[0_30px_80px_rgba(0,0,0,0.45)] transition-transform hover:-translate-y-1">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/shots/dashboard_light_${lang}.png`} alt="" className="w-full rounded-xl" />
            <span className="absolute inset-0 flex items-center justify-center rounded-2xl bg-background/60 opacity-0 backdrop-blur-[2px] transition-opacity group-hover:opacity-100">
              <span className="grad-olive inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-bold text-primary-foreground shadow-lg">
                {c.demo_cta}<ArrowRight className="size-4" />
              </span>
            </span>
          </Link>
        </div>
      </section>

      <section id="how" className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-xs font-bold uppercase tracking-wider text-olive">{c.how_kicker}</div>
        <h2 className="mt-2 text-3xl font-extrabold">{c.how_title}</h2>

        <div className="relative mt-12 grid gap-6 lg:grid-cols-3">
          {/* the thread that ties the three steps together */}
          <div className="pointer-events-none absolute left-0 right-0 top-[26px] hidden h-px bg-gradient-to-r from-transparent via-olive/30 to-transparent lg:block" />

          <Step n={1} h={c.s1_h} p={c.s1_p} chrome={c.s1_chrome}>
            <div className="rounded-lg border border-dashed border-olive/40 bg-olive/[0.04] px-3 py-4 text-center">
              <FileSpreadsheet className="mx-auto size-5 text-olive/70" />
              <div className="mt-1.5 text-[11px] text-muted-foreground">{c.s1_drop}</div>
            </div>
            <div className="mt-2.5 space-y-1.5">
              {c.s1_files.map(([name, meta], i) => (
                <div key={name} className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-2.5 py-1.5">
                  <FileSpreadsheet className="size-3.5 shrink-0 text-olive" />
                  <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium">{name}</span>
                  <span className="shrink-0 text-[10px] text-muted-foreground">{meta}</span>
                  {i < 2 && <Check className="size-3 shrink-0 text-olive" />}
                </div>
              ))}
            </div>
            <div className="mt-3">
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div className="grad-olive h-full w-[78%] rounded-full" />
              </div>
              <div className="mt-1.5 text-[10.5px] font-semibold text-olive">{c.s1_arrow}</div>
            </div>
          </Step>

          <Step n={2} h={c.s2_h} p={c.s2_p} chrome={c.s2_chrome}>
            <div className="space-y-1.5">
              <div className="flex gap-2">
                <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-olive/40 bg-olive/10"><Mark size={11} /></span>
                <div className="rounded-xl rounded-tl-sm bg-secondary/70 px-2.5 py-2 text-[11.5px] leading-snug">{c.s2_q1}</div>
              </div>
              <div className="ml-7 flex flex-wrap gap-1.5">{c.s2_o1.map((o, i) => <Chip key={o} on={i === 1}>{o}</Chip>)}</div>
              <div className="flex justify-end">
                <div className="grad-olive rounded-xl rounded-br-sm px-2.5 py-1.5 text-[11.5px] font-medium text-primary-foreground">{c.s2_a}</div>
              </div>
              <div className="flex gap-2">
                <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-olive/40 bg-olive/10"><Mark size={11} /></span>
                <div className="rounded-xl rounded-tl-sm bg-secondary/70 px-2.5 py-2 text-[11.5px] leading-snug">{c.s2_q2}</div>
              </div>
              <div className="ml-7 flex flex-wrap gap-1.5">{c.s2_o2.map((o, i) => <Chip key={o} on={i === 1}>{o}</Chip>)}</div>
            </div>
          </Step>

          <Step n={3} h={c.s3_h} p={c.s3_p} chrome={c.s3_chrome}>
            <div className="flex flex-wrap gap-1.5">{c.s3_pills.map((o, i) => <Chip key={o} on={i === 3}>{o}</Chip>)}</div>
            <div className="mt-2.5 grid grid-cols-2 gap-2">
              {c.s3_kpis.map(([label, value, delta]) => (
                <div key={label} className="rounded-lg border border-border bg-secondary/40 px-2.5 py-2">
                  <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
                  <div className="text-[15px] font-extrabold tabular-nums leading-tight">{value}</div>
                  <div className="text-[9.5px] font-semibold text-olive">{delta}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 rounded-lg border border-border bg-secondary/30 p-2">
              <svg viewBox="0 0 240 64" className="w-full" role="img" aria-hidden>
                <defs>
                  <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--olive)" stopOpacity="0.45" />
                    <stop offset="100%" stopColor="var(--olive)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[0, 16, 32, 48].map((y) => <line key={y} x1="0" y1={y + 8} x2="240" y2={y + 8} stroke="currentColor" strokeOpacity="0.08" />)}
                {[[10, 34], [40, 26], [70, 38], [100, 18], [130, 30], [160, 12], [190, 22], [214, 8]].map(([x, h]) => (
                  <rect key={x} x={x} y={56 - h} width="14" height={h} rx="3" fill="var(--olive)" fillOpacity={x === 160 ? 1 : 0.55} />
                ))}
                <path d="M17 30 L47 22 L77 33 L107 15 L137 26 L167 9 L197 18 L221 6" fill="none" stroke="var(--olive-light)" strokeWidth="2" strokeLinecap="round" />
                <path d="M17 30 L47 22 L77 33 L107 15 L137 26 L167 9 L197 18 L221 6 L221 56 L17 56 Z" fill="url(#lg)" />
              </svg>
            </div>
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
          <Bento icon={<Blocks />} h={c.b7_h} p={c.b7_p}>
            <div className="mt-4 flex flex-wrap gap-1.5">{c.b7_tags.map((x) => <Chip key={x}>{x}</Chip>)}</div>
          </Bento>
          <Bento icon={<SlidersHorizontal />} h={c.b4_h} p={c.b4_p}>
            <div className="mt-4 flex flex-wrap gap-1.5">{c.s3_pills.map((x) => <Chip key={x}>{x}</Chip>)}</div>
          </Bento>
          <Bento icon={<FileSpreadsheet />} h={c.b5_h} p={c.b5_p} />
          <Bento icon={<Lock />} h={c.b6_h} p={c.b6_p} className="md:col-span-3" />
        </div>
      </section>

      <section id="pricing" className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-xs font-bold uppercase tracking-wider text-olive">{c.price_kicker}</div>
        <h2 className="mt-2 text-3xl font-extrabold">{c.price_title}</h2>
        <p className="mt-2 max-w-2xl text-[14.5px] leading-relaxed text-muted-foreground">{c.price_sub}</p>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[[c.price_free_h, c.price_free_p, c.price_free_note, false],
            [c.price_pro_h, c.price_pro_p, c.price_pro_note, true],
            [c.price_ultra_h, c.price_ultra_p, c.price_ultra_note, false]].map(([h, p, note, hot]) => (
            <div key={h as string} className={`rounded-2xl border bg-card p-6 ${hot ? "border-olive/60 ring-1 ring-olive/30" : "border-border"}`}>
              <h3 className="text-lg font-extrabold">{h as string}</h3>
              <div className="mt-1 text-[15px] font-bold text-olive">{p as string}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{note as string}</p>
            </div>
          ))}
        </div>
        <div className="mt-5">
          <Button variant="outline" nativeButton={false} render={<Link href="/pricing" />}>{c.price_cta}<ArrowRight className="size-4" /></Button>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-4">
        <div className="text-xs font-bold uppercase tracking-wider text-olive">{c.not_kicker}</div>
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <div className="rounded-2xl border border-olive/40 bg-olive/5 p-6">
            <h3 className="text-lg font-bold">{c.for_title}</h3>
            <ul className="mt-3 space-y-2 text-[13.5px] leading-relaxed">
              {c.for_items.map((x) => <li key={x} className="flex gap-2"><span className="text-olive">✓</span>{x}</li>)}
            </ul>
          </div>
          <div className="rounded-2xl border border-border bg-card p-6">
            <h3 className="text-lg font-bold">{c.not_title}</h3>
            <ul className="mt-3 space-y-2 text-[13.5px] leading-relaxed text-muted-foreground">
              {c.not_items.map((x) => <li key={x} className="flex gap-2"><span className="opacity-50">—</span>{x}</li>)}
            </ul>
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-20 pt-10">
        <div className="grad-olive rounded-3xl p-10 text-center text-primary-foreground">
          <h2 className="text-3xl font-extrabold">{c.cta_h}</h2>
          <p className="mt-2 opacity-80">{c.cta_p}</p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Button size="lg" variant="secondary" className="font-bold" nativeButton={false} render={<Link href="/app" />}>{c.cta_btn}<ArrowRight className="size-4" /></Button>
            <Button size="lg" variant="outline" className="border-primary-foreground/40 bg-transparent font-bold text-primary-foreground hover:bg-primary-foreground/10" nativeButton={false} render={<Link href="/demo" />}>{c.demo_cta}</Button>
          </div>
        </div>
      </section>

      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">{c.footer}</footer>
    </div>
  );
}

function Step({ n, h, p, chrome, children }: {
  n: number; h: string; p: string; chrome: string; children: React.ReactNode;
}) {
  return (
    <div className="group relative flex flex-col rounded-2xl border border-border bg-card p-5 transition-all duration-300 hover:-translate-y-1 hover:border-olive/40 hover:shadow-[0_18px_50px_rgba(0,0,0,0.18)]">
      <div className="grad-olive absolute -top-3.5 left-5 inline-flex size-7 items-center justify-center rounded-lg text-[12px] font-extrabold text-primary-foreground shadow-lg">{n}</div>
      {/* a little product window, so the step looks like the app, not a diagram */}
      <div className="mt-2 overflow-hidden rounded-xl border border-border bg-background/70 shadow-inner">
        <div className="flex items-center gap-1.5 border-b border-border bg-secondary/40 px-3 py-1.5">
          <span className="size-1.5 rounded-full bg-muted-foreground/30" />
          <span className="size-1.5 rounded-full bg-muted-foreground/20" />
          <span className="size-1.5 rounded-full bg-muted-foreground/20" />
          <span className="ml-1 truncate text-[10px] font-semibold text-muted-foreground">{chrome}</span>
        </div>
        <div className="flex h-[248px] flex-col justify-center overflow-hidden p-3">{children}</div>
      </div>
      <h3 className="mt-5 text-[17px] font-bold">{h}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">{p}</p>
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
