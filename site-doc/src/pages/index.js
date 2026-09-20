import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import ChatBubble from '@site/src/components/ChatBubble';
import styles from './index.module.css';

function HomepageHeader() {
  return (
    <header className={clsx('hero hero--frase', styles.heroBanner)}>
      <div className="container">
        <div className={styles.heroGrid}>
          <div>
            <Heading as="h1" className={styles.heroTitle}>
              Uma frase por dia, direto no Telegram
            </Heading>
            <p className={styles.heroSubtitle}>
              Todo dia às 8h, a mesma reflexão chega pra você — e pra quem você
              quiser compartilhar. Sem feed, sem rolagem infinita, sem
              algoritmo decidindo o que você vê: só uma frase, escolhida da
              sua própria coleção.
            </p>
            <div className={styles.buttons}>
              <Link className="button button--primary button--lg" to="/docs/como-funciona">
                Como funciona
              </Link>
              <Link
                className="button button--outline button--lg"
                to="https://github.com/soamazyng/frase-diaria-telegram">
                Ver o código
              </Link>
            </div>
          </div>
          <ChatBubble texto="A vitória ama a preparação." autor="Sêneca" />
        </div>
      </div>
    </header>
  );
}

const destaques = [
  {
    titulo: '08:00, todo dia',
    texto: 'Fim de semana incluso. A frase chega no horário certo, sem precisar abrir nada.',
  },
  {
    titulo: 'Nunca repete no ciclo',
    texto: 'A coleção inteira é percorrida antes de qualquer frase repetir.',
  },
  {
    titulo: 'Peça uma extra quando quiser',
    texto: '/frase busca uma nova a qualquer hora, sem atrapalhar a diária.',
  },
  {
    titulo: 'Compartilhe com quem você ama',
    texto: 'A mesma frase, no mesmo instante, para as pessoas que você escolher.',
  },
];

function Destaques() {
  return (
    <section className={styles.destaques}>
      <div className="container">
        <div className={styles.destaquesGrid}>
          {destaques.map((d) => (
            <div key={d.titulo} className={styles.destaqueCard}>
              <Heading as="h3">{d.titulo}</Heading>
              <p>{d.texto}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  return (
    <Layout
      title="Início"
      description="Uma frase por dia, direto no Telegram — documentação e visão de produto do bot pessoal Frase Diária.">
      <HomepageHeader />
      <main>
        <Destaques />
      </main>
    </Layout>
  );
}
