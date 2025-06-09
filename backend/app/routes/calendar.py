from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from bson import ObjectId
from ..database import get_database
from ..middleware.auth_middleware import get_current_user_required as get_current_user  # ✅ CORRETTO
from ..services.database_calendar_service import database_calendar_service  # ✅ MONGODB CALENDAR

router = APIRouter()

@router.get("/bookings", response_model=List[Dict])
async def get_calendar_bookings(
    start_date: str = Query(..., description="Data inizio in formato YYYY-MM-DD"),
    end_date: str = Query(..., description="Data fine in formato YYYY-MM-DD"),
    space_id: Optional[str] = Query(None, description="Filtra per spazio specifico"),
    current_user: dict = Depends(get_current_user)  # ✅ CORRETTO
):
    """
    Recupera tutte le prenotazioni per il calendario condiviso MongoDB
    Visibile a tutti gli utenti dell'applicazione
    """
    try:
        # Converte le date
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        # ✅ USA IL CALENDARIO DATABASE MONGODB
        events = await database_calendar_service.get_calendar_events(
            start_dt, end_dt, space_id
        )
        
        # Trasforma eventi calendario in formato compatibile con frontend
        calendar_bookings = []
        for event in events:
            # Recupera dettagli dall'evento calendario
            booking_data = {
                "id": event.get("booking_id", event["id"]),
                "space_id": event["space_id"],
                "space_name": event["space_name"],
                "space_location": event["location"],
                "user_id": event.get("created_by_email", "sistema"),
                "user_name": "Utente Sistema",  # Placeholder
                "user_role": "student",
                "start_datetime": event["start_datetime"].isoformat(),
                "end_datetime": event["end_datetime"].isoformat(),
                "purpose": event["purpose"],
                "status": "confirmed",  # Eventi nel calendario MongoDB sono sempre confermati
                "materials_requested": event.get("materials_requested", []),
                "notes": event.get("notes", ""),
                "created_at": event.get("start_datetime", datetime.utcnow()).isoformat(),
                "is_own_booking": False  # Privacy: solo info pubbliche
            }
            
            # Se c'è un booking_id, recupera dettagli utente dal database
            if event.get("booking_id"):
                try:
                    db = await get_database()
                    booking = await db.bookings.find_one({"_id": ObjectId(event["booking_id"])})
                    if booking:
                        user = await db.users.find_one({"_id": ObjectId(booking["user_id"])})
                        if user:
                            booking_data.update({
                                "user_id": booking["user_id"],
                                "user_name": user["full_name"],
                                "user_role": user.get("role", "student"),
                                "status": booking["status"],
                                "is_own_booking": str(booking["user_id"]) == str(current_user["_id"])
                            })
                            
                            # Privacy: nascondi dettagli se non è la propria prenotazione
                            if not booking_data["is_own_booking"]:
                                booking_data["notes"] = ""
                                if len(booking_data["purpose"]) > 50:
                                    booking_data["purpose"] = booking_data["purpose"][:50] + "..."
                                    
                except Exception as e:
                    print(f"⚠️ Errore recupero dettagli booking {event.get('booking_id')}: {e}")
            
            calendar_bookings.append(booking_data)
        
        return calendar_bookings
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nel recupero prenotazioni: {str(e)}")

@router.get("/availability/{space_id}")
async def get_space_availability(
    space_id: str,
    date: str = Query(..., description="Data in formato YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user)  # ✅ CORRETTO
):
    """
    Verifica disponibilità dettagliata di uno spazio per una data specifica usando MongoDB
    """
    try:
        # Converte la data
        check_date = datetime.strptime(date, "%Y-%m-%d")
        
        # ✅ USA IL CALENDARIO DATABASE MONGODB
        availability = await database_calendar_service.get_space_availability_calendar(
            space_id, check_date
        )
        
        if "error" in availability:
            raise HTTPException(status_code=404, detail=availability["error"])
        
        return availability
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella verifica disponibilità: {str(e)}")

@router.get("/stats")
async def get_calendar_stats(
    current_user: dict = Depends(get_current_user)  # ✅ CORRETTO
):
    """
    Statistiche del calendario per dashboard (da MongoDB)
    """
    try:
        db = await get_database()
        
        now = datetime.now()
        today_start = datetime.combine(now.date(), datetime.min.time())
        today_end = datetime.combine(now.date(), datetime.max.time())
        week_start = today_start - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        
        # ✅ STATISTICHE DAL CALENDARIO MONGODB
        today_events = await database_calendar_service.get_calendar_events(
            today_start, today_end
        )
        
        week_events = await database_calendar_service.get_calendar_events(
            week_start, week_end
        )
        
        month_events = await database_calendar_service.get_calendar_events(
            month_start, next_month
        )
        
        # Conta per tipo di evento
        today_bookings = len([e for e in today_events if e.get("event_type") == "booking"])
        week_bookings = len([e for e in week_events if e.get("event_type") == "booking"])
        month_bookings = len([e for e in month_events if e.get("event_type") == "booking"])
        
        # Spazi più utilizzati questo mese
        space_usage = {}
        for event in month_events:
            if event.get("event_type") == "booking" and event.get("space_id"):
                space_id = event["space_id"]
                space_usage[space_id] = space_usage.get(space_id, 0) + 1
        
        # Trasforma in lista ordinata
        popular_spaces = []
        for space_id, count in sorted(space_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
            try:
                space = await db.spaces.find_one({"_id": ObjectId(space_id)})
                if space:
                    popular_spaces.append({
                        "space_id": space_id,
                        "space_name": space["name"],
                        "booking_count": count
                    })
            except:
                continue
        
        # Prossime prenotazioni per l'utente corrente
        user_next_bookings = []
        try:
            user_bookings = await db.bookings.find({
                "user_id": str(current_user["_id"]),
                "start_datetime": {"$gte": now},
                "status": {"$in": ["confirmed", "pending"]}
            }).sort("start_datetime", 1).limit(3).to_list(3)
            
            for booking in user_bookings:
                space = await db.spaces.find_one({"_id": ObjectId(booking["space_id"])})
                user_next_bookings.append({
                    "id": str(booking["_id"]),
                    "space_name": space["name"] if space else "Spazio eliminato",
                    "start_datetime": booking["start_datetime"].isoformat(),
                    "purpose": booking["purpose"]
                })
        except Exception as e:
            print(f"⚠️ Errore recupero prossime prenotazioni utente: {e}")
        
        return {
            "today_bookings": today_bookings,
            "week_bookings": week_bookings,
            "month_bookings": month_bookings,
            "popular_spaces": popular_spaces,
            "user_next_bookings": user_next_bookings,
            "last_updated": now.isoformat(),
            "calendar_source": "MongoDB Database"  # ✅ Indica che usa MongoDB
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nel recupero statistiche: {str(e)}")

@router.post("/bulk-availability")
async def check_bulk_availability(
    request_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)  # ✅ CORRETTO
):
    """
    Verifica disponibilità di più spazi per più date usando MongoDB
    """
    try:
        space_ids = request_data.get("space_ids", [])
        dates = request_data.get("dates", [])
        start_time = request_data.get("start_time", "09:00")
        end_time = request_data.get("end_time", "11:00")
        
        if not space_ids or not dates:
            raise HTTPException(status_code=400, detail="space_ids e dates sono obbligatori")
        
        results = []
        
        for space_id in space_ids:
            db = await get_database()
            space = await db.spaces.find_one({"_id": ObjectId(space_id)})
            if not space:
                continue
                
            space_result = {
                "space_id": space_id,
                "space_name": space["name"],
                "space_location": space["location"],
                "availability": []
            }
            
            for date_str in dates:
                try:
                    check_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    # ✅ USA CALENDARIO MONGODB PER VERIFICA DISPONIBILITÀ
                    availability = await database_calendar_service.get_space_availability_calendar(
                        space_id, check_date
                    )
                    
                    if "error" in availability:
                        space_result["availability"].append({
                            "date": date_str,
                            "available": False,
                            "conflict_reason": availability["error"]
                        })
                        continue
                    
                    # Verifica slot specifico
                    conflict = False
                    conflict_reason = None
                    
                    for slot in availability.get("time_slots", []):
                        if (slot["start_time"] <= start_time < slot["end_time"] or
                            slot["start_time"] < end_time <= slot["end_time"]):
                            if not slot["available"]:
                                conflict = True
                                conflict_reason = "Spazio già occupato"
                                break
                    
                    space_result["availability"].append({
                        "date": date_str,
                        "available": not conflict,
                        "conflict_reason": conflict_reason
                    })
                    
                except ValueError:
                    space_result["availability"].append({
                        "date": date_str,
                        "available": False,
                        "conflict_reason": "Formato data non valido"
                    })
                except Exception as e:
                    space_result["availability"].append({
                        "date": date_str,
                        "available": False,
                        "conflict_reason": f"Errore: {str(e)}"
                    })
            
            results.append(space_result)
        
        return {
            "results": results,
            "calendar_source": "MongoDB Database"  # ✅ Indica che usa MongoDB
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella verifica bulk: {str(e)}")

@router.post("/system-events")
async def add_system_event(
    event_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)  # ✅ CORRETTO
):
    """
    Aggiunge eventi di sistema (manutenzioni, chiusure, etc.) al calendario MongoDB
    Solo per admin
    """
    try:
        # Verifica permessi admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Solo gli amministratori possono aggiungere eventi di sistema")
        
        title = event_data.get("title")
        description = event_data.get("description", "")
        start_datetime = datetime.fromisoformat(event_data.get("start_datetime"))
        end_datetime = datetime.fromisoformat(event_data.get("end_datetime"))
        event_type = event_data.get("event_type", "system")
        
        # ✅ AGGIUNGI EVENTO AL CALENDARIO MONGODB
        success = await database_calendar_service.add_system_event(
            title, description, start_datetime, end_datetime, event_type
        )
        
        if success:
            return {
                "status": "success",
                "message": f"Evento di sistema '{title}' aggiunto al calendario MongoDB",
                "calendar_source": "MongoDB Database"
            }
        else:
            raise HTTPException(status_code=500, detail="Errore nell'aggiunta dell'evento di sistema")
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Formato datetime non valido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nell'aggiunta evento sistema: {str(e)}")