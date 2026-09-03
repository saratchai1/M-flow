export default async function handler(req, res) {
  const target = 'https://mflowthai.com/mflow/unuserpayment';
  try {
    const response = await fetch(target, {
      redirect: 'follow',
      headers: {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'th-TH,th;q=0.9,en;q=0.8',
        'cache-control': 'no-cache',
      },
    });
    const text = await response.text();
    res.status(200).json({
      reachable: response.ok,
      upstreamStatus: response.status,
      finalUrl: new URL(response.url).origin + new URL(response.url).pathname,
      title: (text.match(/<title[^>]*>([^<]*)<\/title>/i) || [null, null])[1],
      bodyHead: text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 500),
    });
  } catch (error) {
    res.status(200).json({reachable:false,error:String(error)});
  }
}
