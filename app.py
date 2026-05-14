import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
from datetime import datetime, timedelta

load_dotenv(dotenv_path="pass.env")
app = Flask(__name__)
app.secret_key = "maya_ozel_anahtar"

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"), 
        database=os.getenv("DB_NAME", "RestoranDB")
    )

@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM MASA ORDER BY Masa_ID ASC")
    masalar = cursor.fetchall()
    simdi = datetime.now()
    bugun_bas = simdi.replace(hour=0, minute=0, second=0)
    bugun_bit = simdi.replace(hour=23, minute=59, second=59)
    cursor.execute("SELECT Masa_ID, Tarih FROM REZERVASYON WHERE Tarih BETWEEN %s AND %s", (bugun_bas, bugun_bit))
    gunluk_rezler = cursor.fetchall()
    for m in masalar:
        m['durum'] = 'bos'
        for r in gunluk_rezler:
            if r['Masa_ID'] == m['Masa_ID']:
                if simdi >= r['Tarih'] - timedelta(hours=1) and simdi <= r['Tarih'] + timedelta(hours=2):
                    m['durum'] = 'dolu'
                elif r['Tarih'] > simdi:
                    m['durum'] = 'rezerve'
    cursor.close()
    db.close()
    return render_template('index.html', masalar=masalar, sayfa='genel')

@app.route('/masalar')
def masalar_listesi():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM MASA ORDER BY Masa_ID ASC")
    masalar = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('masalar.html', masalar=masalar, sayfa='masa')



@app.route('/menu')
def menu_listesi():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # Ürünleri ID sırasına göre çekiyoruz
    cursor.execute("SELECT * FROM urun ORDER BY Urun_Id ASC")
    urunler = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('menu.html', urunler=urunler, sayfa='menu')

@app.route('/siparisler')
def siparis_listesi():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # Aktif siparişleri çek
    cursor.execute("SELECT s.*, m.Konum FROM SIPARIS s JOIN MASA m ON s.Masa_Id = m.Masa_Id")
    siparisler = cursor.fetchall()
    # Ürünleri (Menüyü) çek - Seçim kutusu için
    cursor.execute("SELECT * FROM urun ORDER BY Urun_Adi ASC")
    urunler = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('siparisler.html', siparisler=siparisler, urunler=urunler, sayfa='siparis')


@app.route('/rezervasyon-olustur', methods=['POST'])
def rezervasyon_olustur():
    # 1. Form Verilerini Al
    ad = request.form.get('ad')
    soyad = request.form.get('soyad')
    telefon = request.form.get('telefon')
    tarih = request.form.get('tarih')
    saat = request.form.get('saat')
    kisi_sayisi = int(request.form.get('kisi_sayisi'))
    masa_id = request.form.get('masa_id')

    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # 2. Kapasite Kontrolü Yap [cite: 16, 22]
        cursor.execute("SELECT Kapasite FROM MASA WHERE Masa_ID = %s", (masa_id,))
        masa = cursor.fetchone()

        if not masa:
            flash(f"Hata: {masa_id} numaralı masa bulunamadı!", "danger")
            return redirect(url_for('index'))

        # Karşılaştırma: Kişi sayısı > Kapasite mi? 
        if kisi_sayisi > masa['Kapasite']:
            flash(f"⚠️ Kapasite Yetersiz! Masa {masa_id} en fazla {masa['Kapasite']} kişiliktir. {kisi_sayisi} kişi için ek masa ayarlanmalı veya daha büyük bir masa seçilmelidir.", "danger")
            return redirect(url_for('index'))

        # 3. Müşteriyi Kaydet [cite: 6, 8, 9, 10, 11]
        cursor.execute(
            "INSERT INTO MUSTERI (Ad, Soyad, Telefon) VALUES (%s, %s, %s)",
            (ad, soyad, telefon)
        )
        musteri_id = cursor.lastrowid # Yeni oluşan müşteri ID'sini al [cite: 18]

        # 4. Rezervasyonu Kaydet [cite: 12, 14, 15]
        tam_tarih = f"{tarih} {saat}:00"
        cursor.execute(
            "INSERT INTO REZERVASYON (Tarih, Kisi_Sayisi, Musteri_ID, Masa_ID) VALUES (%s, %s, %s, %s)",
            (tam_tarih, kisi_sayisi, musteri_id, masa_id)
        )

        db.commit() # Veritabanına işle
        flash(f"Başarılı! {ad} {soyad} için Masa {masa_id} rezerve edildi.", "success")

    except Exception as e:
        db.rollback() # Hata olursa işlemi geri al
        flash(f"Sistem Hatası: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('index'))


@app.route('/kapasite-kontrol')
def kapasite_kontrol():
    masa_id = request.args.get('masa_id')
    kisi = int(request.args.get('kisi', 0))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT Kapasite FROM MASA WHERE Masa_ID = %s", (masa_id,))
    masa = cursor.fetchone()
    cursor.close()
    db.close()

    if masa and kisi > masa['Kapasite']:
        return {"uygun": False, "kapasite": masa['Kapasite']}
    return {"uygun": True}


# --- MÜŞTERİ VE REZERVASYON İŞLEMLERİ ---

@app.route('/musteriler')
def musteri_listesi():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # Veritabanındaki sütun adlarına dikkat (Musteri_ID, Masa_ID)
    query = """
        SELECT M.Musteri_ID, M.Ad, M.Soyad, R.Tarih, R.Masa_ID 
        FROM MUSTERI M
        LEFT JOIN REZERVASYON R ON M.Musteri_ID = R.Musteri_ID
        ORDER BY M.Musteri_ID DESC
    """
    cursor.execute(query)
    musteriler = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('musteri.html', musteriler=musteriler)

@app.route('/rezervasyon_guncelle/<int:musteri_id>', methods=['POST'])
def rezervasyon_guncelle(musteri_id):
    tarih = request.form.get('tarih')
    saat = request.form.get('saat')
    masa_id = request.form.get('masa_id')
    tam_tarih = f"{tarih} {saat}:00"
    
    db = get_db()
    cursor = db.cursor()
    try:
        # Önce bu müşterinin rezervasyonu var mı bak
        cursor.execute("SELECT Rezerve_ID FROM REZERVASYON WHERE Musteri_ID = %s", (musteri_id,))
        rez = cursor.fetchone()

        if rez:
            # Varsa GÜNCELLE [cite: 12, 14, 15]
            cursor.execute("""
                UPDATE REZERVASYON 
                SET Tarih = %s, Masa_ID = %s 
                WHERE Musteri_ID = %s
            """, (tam_tarih, masa_id, musteri_id))
        else:
            # Yoksa YENİ OLUŞTUR (Kişi sayısı varsayılan 2) [cite: 16]
            cursor.execute("""
                INSERT INTO REZERVASYON (Tarih, Masa_ID, Musteri_ID, Kisi_Sayisi) 
                VALUES (%s, %s, %s, 2)
            """, (tam_tarih, masa_id, musteri_id))
            
        db.commit()
        flash("Veritabanı başarıyla güncellendi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Hata: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for('musteri_listesi'))

@app.route('/musteri_sil/<int:musteri_id>', methods=['POST'])
def musteri_sil(musteri_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # 1. Önce REZERVASYON silinmeli (Foreign Key engeline takılmamak için) [cite: 12]
        cursor.execute("DELETE FROM REZERVASYON WHERE Musteri_ID = %s", (musteri_id,))
        
        # 2. Sonra MUSTERI silinmeli [cite: 6]
        cursor.execute("DELETE FROM MUSTERI WHERE Musteri_ID = %s", (musteri_id,))
        
        db.commit()
        flash("Kayıtlar veritabanından tamamen silindi.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Silme Hatası: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for('musteri_listesi'))




if __name__ == '__main__':
    app.run(debug=True)